import collections
import json
import time
import urllib.parse
import urllib.robotparser
from bs4 import BeautifulSoup
import requests

class PoliteCrawler:
    def __init__(
        self,
            start_url:str,
            user_agent:str = "AyushBot/1.0",
            max_pages:int = 10,
            max_depth:int = 2,
            delay_seconds:float = 1.0,
            timeout_seconds:float = 5.0,
    ):
        self.start_url = start_url
        self.user_agent = user_agent
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds

        parsed = urllib.parse.urlparse(start_url)
        self.allowed_domain = parsed.netloc.lower()
        self.scheme = parsed.scheme.lower()

        self.frontier = collections.deque([(start_url,0)])
        self.visited = set()
        self.crawled_data = []

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

        self.robot_parser = urllib.robotparser.RobotFileParser()
        self._init_robots_txt()

    def _init_robots_txt(self) -> None:
        robots_url = f"{self.scheme}://{self.allowed_domain}/robots.txt"
        self.robot_parser.set_url(robots_url)
        try:
            resp = self.session.get(robots_url , timeout=self.timeout_seconds)
            if resp.status_code == 200:
                self.robot_parser.parse(resp.text.splitlines())
                print(f"[ROBOTS] Loaded rules from {robots_url}")
            elif resp.status_code in (401,403):
                self.robot_parser.disallow_all = True
                print(f"[ROBOTS] Disallow all (HTTP {resp.status_code})")
            else:
                self.robot_parser.allow_all = True
                print(f"[ROBOTS] Allow all (HTTP {resp.status_code})")
        except requests.RequestException as err:
            self.robot_parser.allow_all = True
            print (f"[ROBOTS] Failed to load ({err}). Defaulting to allow")

    def can_fetch(self,url:str) -> bool:
        return self.robot_parser.can_fetch(self.user_agent , url)

    def normalize_url(self, base_url:str , href:str) -> str | None:
        joined = urllib.parse.urljoin(base_url,href)
        parsed = urllib.parse.urlsplit(joined)

        if parsed.scheme.lower() not in ("http" , "https"):
            return None

        if parsed.netloc.lower() != self.allowed_domain:
            return None

        normalized = urllib.parse.urlunsplit((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            parsed.query,
            "" #Strip fragment
        ))
        return normalized

    def extract_links(self,base_url:str , html:str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for tag in soup.find_all("a" , href=True):
            clean_url = self.normalize_url(base_url , tag["href"])
            if clean_url:
                links.append(clean_url)
        return links

    def fetch_page(self,url:str) -> str | None:
        try:
            resp = self.session.get(url, timeout=self.timeout_seconds)
            if resp.status_code ==200:
                content_type = resp.headers.get("Content-Type" , "").lower()
                if "text/html" in content_type:
                    return resp.text
            elif resp.status_code ==429 or resp.status_code >=500:
                print(f"[THROTTLE] HTTP {resp.status_code} on {url}. Backing off.")
                time.sleep(self.delay_seconds * 20)
            return None
        except requests.RequestException as err:
            print(f"[ERROR] Fetch failed on {url}: {err}")
            return None

    def crawl(self) -> list[dict]:
        print(f"[START] Beginning crawl on {self.start_url}")
        while self.frontier and len(self.visited) < self.max_pages:
            url,depth = self.frontier.popleft()

            if url in self.visited:
                continue
            
            if depth > self.max_depth:
                continue

            if not self.can_fetch(url):
                print(f"[BLOCKED] Disallowed by robots.txt: {url}")
                self.visited.add(url)
                continue

            time.sleep(self.delay_seconds)
            html = self.fetch_page(url)
            self.visited.add(url)

            if html is None:
                continue

            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else ""

            self.crawled_data.append({
                "url":url,
                "title":title,
                "depth":depth,
                "crawled_at":time.strftime("%Y-%m-%dT%H:%M:%SZ" , time.gmtime()),
                "html_bytes":len(html),
            })
            print(f"[FETCHED] {url} (Depth {depth}) -> '{title[:40]}'")

            if depth < self.max_depth:
                outbound = self.extract_links(url,html)
                for link in outbound:
                    if link not in self.visited:
                        self.frontier.append((link,depth+1))

        print(f"[COMPLETE] Crawled {len(self.crawled_data)} pages. Visited {len(self.visited)} URLs. ")
        return self.crawled_data

    def save_json(self,output_path:str = "crawl_results.json") -> None:
            with open(output_path , "w" , encoding="utf-8") as f:
                json.dump(self.crawled_data , f , indent=2 , ensure_ascii=False)
            print(f"[SAVED] Results exported to {output_path}")

if __name__ == "__main__":
    target = "https://example.com"
    crawler = PoliteCrawler(
        start_url=target,
            max_pages=5,
            max_depth=2,
            delay_seconds=1.0
    )
    crawler.crawl()
    crawler.save_json("example_crawl.json")
