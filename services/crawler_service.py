import requests
from bs4 import BeautifulSoup
import re
import time
from models.movie import Movie
from models.director import Director
from services.movie_service import MovieService
from services.director_service import DirectorService

class CrawlerService:
    def __init__(self):
        self.movie_service = MovieService()
        self.director_service = DirectorService()
        self.base_url = "https://en.wikipedia.org"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }

        self._director_cache: dict[str, Director] = {}

    def _get_page(self, url: str):
        try:
            res = requests.get(url, headers=self.headers, timeout=10)
            res.raise_for_status()
            return BeautifulSoup(res.text, "html.parser")
        except Exception as e:
            print(f"  [WARN] Không tải được {url}: {e}")
            return None

    def _get_director_birth_year(self, director_url: str):
        if not director_url:
            return None

        soup = self._get_page(self.base_url + director_url)
        if not soup:
            return None

        # Ưu tiên 1: thẻ <span class="bday"> (ISO 8601)
        bday = soup.find(class_="bday")
        if bday:
            m = re.search(r"\d{4}", bday.text)
            if m:
                return int(m.group())

        # Ưu tiên 2: hàng "Born" trong infobox
        infobox = soup.find("table", {"class": "infobox"})
        if infobox:
            for tr in infobox.find_all("tr"):
                th = tr.find("th")
                if th and "Born" in th.get_text():
                    td = tr.find("td")
                    if td:
                        m = re.search(r"\d{4}", td.get_text())
                        if m:
                            return int(m.group())
        return None

    def _get_director_info_from_movie_page(self, movie_url: str):
        soup = self._get_page(self.base_url + movie_url)
        if not soup:
            return "Unknown Director", None

        infobox = soup.find("table", {"class": "infobox"})
        if not infobox:
            return "Unknown Director", None
        for tr in infobox.find_all("tr"):
            th = tr.find("th")
            if th and "Directed by" in th.get_text():
                td = tr.find("td")
                if not td:
                    continue
                link = td.find("a")
                if link:
                    name = link.get_text(strip=True)
                    url = link.get("href")
                else:
                    name = td.get_text(separator="\n").strip().split("\n")[0].strip()
                    url = None
                return name or "Unknown Director", url

        return "Unknown Director", None

    def _get_or_create_director(self, name: str, birth_year) -> Director:
        if name in self._director_cache:
            director = self._director_cache[name]
            # Cập nhật birth_year nếu chưa có
            if birth_year and director.birth_year != birth_year:
                director.birth_year = birth_year
                self.director_service.repo.update(director)
            return director

        all_directors = self.director_service.get_all_directors()
        existing = next((d for d in all_directors if d.name == name), None)

        if existing:
            if birth_year and existing.birth_year != birth_year:
                existing.birth_year = birth_year
                self.director_service.repo.update(existing)
            self._director_cache[name] = existing
            return existing

        new_dir = self.director_service.add_director(
            Director(name=name, birth_year=birth_year)
        )
        self._director_cache[name] = new_dir
        return new_dir

    def crawl_movies(self, limit: int = 50) -> int:
        self._director_cache.clear()

        url = "https://en.wikipedia.org/wiki/List_of_highest-grossing_films"
        count = 0

        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            print(f"[ERROR] Không tải được trang Wikipedia: {e}")
            return self.seed_initial_data()

        table = soup.find("table", {"class": "wikitable"})
        if not table:
            print("[WARN] Không tìm thấy bảng wikitable, dùng dữ liệu mẫu.")
            return self.seed_initial_data()

        rows = table.find_all("tr")[1:]  # Bỏ header

        for row in rows:
            if count >= limit:
                break

            try:
                cols = row.find_all(["td", "th"])
                if len(cols) < 5:
                    continue

                # --- Tiêu đề ---
                title_cell = cols[2]
                title_link = title_cell.find("a")
                title = (
                    title_link.get_text(strip=True)
                    if title_link
                    else title_cell.get_text(strip=True)
                )
                title = re.sub(r"[†*]|\s*\[.*?\]", "", title).strip()
                if not title:
                    continue

                movie_url = title_link.get("href") if title_link else None

                # --- Doanh thu ---
                gross_text = cols[3].get_text(strip=True)
                gross_match = re.search(r"\$([\d,]+)", gross_text)
                revenue = (
                    float(gross_match.group(1).replace(",", ""))
                    if gross_match
                    else 0.0
                )

                # --- Năm ---
                year_match = re.search(r"\d{4}", cols[4].get_text(strip=True))
                year = int(year_match.group()) if year_match else 2024

                # --- Đạo diễn ---
                director_name = "Unknown"
                birth_year = None
                if movie_url:
                    print(f"[{count+1}/{limit}] Đang xử lý: {title}")
                    director_name, director_url = self._get_director_info_from_movie_page(movie_url)
                    if director_url:
                        print(f"  -> Tìm năm sinh: {director_name}...")
                        birth_year = self._get_director_birth_year(director_url)
                    # FIX 3: Delay sau mỗi phim để tránh bị Wikipedia block
                    time.sleep(0.5)

                director = self._get_or_create_director(director_name, birth_year)

                # --- Lưu phim ---
                self.movie_service.add_movie(
                    Movie(
                        title=title,
                        year=year,
                        revenue=revenue,
                        director_id=director.id,
                    )
                )
                count += 1

            except Exception as e:
                print(f"  [SKIP] Bỏ qua dòng lỗi: {e}")
                continue

        if count == 0:
            print("[WARN] Không crawl được phim nào, dùng dữ liệu mẫu.")
            return self.seed_initial_data()

        print(f"[OK] Crawl xong: {count} phim.")
        return count

    def seed_initial_data(self) -> int:
        self._director_cache.clear()
        sample = [
            ("Avatar",                2009, 2_923_706_026.0, "James Cameron",   1954),
            ("Avengers: Endgame",     2019, 2_797_501_328.0, "Anthony Russo",   1970),
            ("Avatar: The Way of Water", 2022, 2_320_250_281.0, "James Cameron", 1954),
            ("Titanic",               1997, 2_257_844_554.0, "James Cameron",   1954),
            ("Star Wars: The Force Awakens", 2015, 2_068_223_624.0, "J.J. Abrams", 1966),
            ("Avengers: Infinity War", 2018, 2_048_359_754.0, "Anthony Russo",  1970),
            ("Ne Zha 2",              2025, 1_900_000_000.0, "Jiaozi",          1981),
            ("Spider-Man: No Way Home", 2021, 1_901_216_740.0, "Jon Watts",     1981),
            ("Jurassic World",        2015, 1_671_713_208.0, "Colin Trevorrow", 1976),
            ("The Lion King",         2019, 1_663_075_401.0, "Jon Favreau",     1966),
        ]
        count = 0
        for title, year, rev, d_name, d_year in sample:
            try:
                director = self._get_or_create_director(d_name, d_year)
                self.movie_service.add_movie(
                    Movie(title=title, year=year, revenue=rev, director_id=director.id)
                )
                count += 1
            except Exception as e:
                print(f"  [SKIP] seed '{title}': {e}")
        print(f"[OK] Seed xong: {count} phim mẫu.")
        return count
