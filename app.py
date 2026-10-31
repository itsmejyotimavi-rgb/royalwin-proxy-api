import time
import threading
import requests
import re
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="RoyalWin High-Speed Live Draw API", version="1.0")

# Enable CORS so any web or desktop client can access it freely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOMAINS = [
    "www.royalwin1.com",
    "www.royalwin2.com",
    "www.royalwin3.com",
    "www.royalwin4.com",
    "www.royalwin5.com",
    "www.royalwin7.com",
    "www.royalwin8.com",
    "www.royalwin9.com"
]

GAME_MAP = {
    "15s": "SELF_MONEY_TREE_15S",
    "30s": "SELF_MONEY_TREE_30S",
    "1m": "SELF_MONEY_TREE",
    "SELF_MONEY_TREE_15S": "SELF_MONEY_TREE_15S",
    "SELF_MONEY_TREE_30S": "SELF_MONEY_TREE_30S",
    "SELF_MONEY_TREE": "SELF_MONEY_TREE",
}

# In-memory fast cache
CACHE = {
    "SELF_MONEY_TREE_15S": None,
    "SELF_MONEY_TREE_30S": None,
    "SELF_MONEY_TREE": None,
}

class FastFetcher:
    def __init__(self):
        self.active_domain_idx = 0
        self.session = None
        self.last_auth_time = 0
        self.lock = threading.RLock()
        self._reset_session()
        self._init_cookies("SELF_MONEY_TREE_30S")

    @property
    def domain(self):
        return DOMAINS[self.active_domain_idx]

    def _reset_session(self):
        with self.lock:
            if self.session:
                try:
                    self.session.close()
                except Exception:
                    pass
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json',
                'Origin': f'https://{self.domain}',
                'Referer': f'https://{self.domain}/lottery-bet/SELF_MONEY_TREE_30S'
            })

    def _init_cookies(self, game_id="SELF_MONEY_TREE_30S"):
        with self.lock:
            start_idx = self.active_domain_idx
            num = len(DOMAINS)
            for offset in range(num):
                idx = (start_idx + offset) % num
                target = DOMAINS[idx]
                try:
                    self.active_domain_idx = idx
                    self.session.headers['Origin'] = f'https://{target}'
                    self.session.headers['Referer'] = f'https://{target}/lottery-bet/{game_id}'
                    self.session.cookies.clear()

                    auth_url = f'https://{target}/security/auth?url=%2Flottery-bet%2F{game_id}'
                    r = self.session.get(auth_url, timeout=3.5)
                    if r.status_code == 200:
                        cct_list = re.findall(r'cct[="]+([0-9a-f]{32})', r.text)
                        r_list = re.findall(r'r=(\d+)', r.text)
                        if cct_list and r_list:
                            self.session.cookies.set('cct', cct_list[-1], domain=target, path='/')
                            self.session.cookies.set('r', r_list[-1], domain=target, path='/')
                            self.last_auth_time = time.time()
                            return True
                except Exception:
                    continue
            return False

    def fetch(self, game_id):
        with self.lock:
            now = time.time()
            if (now - self.last_auth_time) > 480:
                self._reset_session()
                self._init_cookies(game_id)

            payload = {'gameId': game_id, 'platform': 'PC', 'siteId': 'sun'}
            for _ in range(2):
                url = f'https://{self.domain}/fg/api/v0/real_time_lottery.do'
                try:
                    res = self.session.post(url, json=payload, timeout=3.5)
                    if res.status_code == 200:
                        data = res.json()
                        cur_list = data.get('currentLotteries', [])
                        current_issue = cur_list[0].get('issue') if cur_list else None

                        latest = data.get('latestDraws', [])
                        if latest:
                            draw = latest[0]
                            issue = draw.get('issue')
                            draw_results = draw.get('drawResults', [])
                            if draw_results and len(draw_results[0]) > 0:
                                last_item = draw_results[0][-1]
                                num_str = last_item.get('name')
                                if num_str and num_str.isdigit():
                                    num = int(num_str)
                                    dice = [x.get('name') for x in draw_results[0] if x.get('viewType') == 'N']
                                    size = "L" if num >= 11 else "S"
                                    oe = "O" if (num % 2 == 1) else "E"
                                    return {
                                        "status": "ok",
                                        "gameId": game_id,
                                        "issue": str(issue),
                                        "next_issue": str(current_issue) if current_issue else str(int(issue) + 1),
                                        "num": num,
                                        "dice": dice,
                                        "size": size,
                                        "oe": oe,
                                        "updated_at": round(time.time(), 3)
                                    }
                    elif res.status_code in (401, 403, 302, 404, 502, 503):
                        self.active_domain_idx = (self.active_domain_idx + 1) % len(DOMAINS)
                        self._reset_session()
                        self._init_cookies(game_id)
                except Exception:
                    self.active_domain_idx = (self.active_domain_idx + 1) % len(DOMAINS)
                    self._reset_session()
                    self._init_cookies(game_id)
            return None

fetcher = FastFetcher()

def background_sync_worker():
    """Background worker continuously refreshing the memory cache so client responses are sub-millisecond."""
    while True:
        for gid in ["SELF_MONEY_TREE_15S", "SELF_MONEY_TREE_30S", "SELF_MONEY_TREE"]:
            try:
                res = fetcher.fetch(gid)
                if res:
                    CACHE[gid] = res
            except Exception:
                pass
            time.sleep(0.5)
        time.sleep(1.0)

# Start background sync
threading.Thread(target=background_sync_worker, daemon=True).start()

@app.get("/")
def home():
    return {
        "status": "online",
        "service": "RoyalWin Live Lottery Proxy API",
        "supported_games": ["15s", "30s", "1m"],
        "endpoints": {
            "draw": "/api/draw?game=15s",
            "all": "/api/all"
        }
    }

@app.get("/api/draw")
def get_draw(game: str = Query("30s", description="15s, 30s, or 1m")):
    canonical = GAME_MAP.get(game.lower(), "SELF_MONEY_TREE_30S")
    cached = CACHE.get(canonical)
    if cached:
        return cached
    # Fallback to direct fetch if cache warming up
    res = fetcher.fetch(canonical)
    if res:
        CACHE[canonical] = res
        return res
    return {"status": "error", "message": "Failed to fetch draw, retrying..."}

@app.get("/api/all")
def get_all():
    return {
        "status": "ok",
        "15s": CACHE.get("SELF_MONEY_TREE_15S"),
        "30s": CACHE.get("SELF_MONEY_TREE_30S"),
        "1m": CACHE.get("SELF_MONEY_TREE")
    }

