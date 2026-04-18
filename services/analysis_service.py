import matplotlib
matplotlib.use('Agg') # Ngăn lỗi 'main thread is not in main loop' trên Flask
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import io
import base64
from repositories.movie_repo import MovieRepository
from repositories.director_repo import DirectorRepository

def _get_vietnamese_font():
    preferred = [
        "Arial", "Segoe UI", "Tahoma",         # Windows
        "DejaVu Sans",                         # Linux / fallback
        "Helvetica Neue", "Helvetica",         # macOS
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for font in preferred:
        if font in available:
            return font
    return "DejaVu Sans"


CHART_FONT = _get_vietnamese_font()

BAR_COLORS = [
    "#ffc107", "#17a2b8", "#dc3545", "#007bff",
    "#6610f2", "#28a745", "#fd7e14", "#e83e8c",
]

class AnalysisService:
    def __init__(self):
        self.movie_repo = MovieRepository()
        self.director_repo = DirectorRepository()

    def get_statistics(self, search_query=None, sort_by=None, director_id=None):
        movies = self.movie_repo.get_all(search_query=search_query, sort_by=sort_by, director_id=director_id)
        if not movies:
            return {"count": 0, "total_revenue": 0, "avg_revenue": 0, "top_movies": []}
            
        total_rev = sum(m.revenue for m in movies if m.revenue)
        avg_rev = total_rev / len(movies)
        # Sắp xếp theo doanh thu giảm dần để lấy Top 5
        top_movies = sorted(movies, key=lambda x: x.revenue, reverse=True)[:5]
        
        return {
            "count": len(movies),
            "total_revenue": round(total_rev, 2),
            "avg_revenue": round(avg_rev, 2),
            "top_movies": top_movies
        }

    def generate_charts(self, director_id=None):
         movies = self.movie_repo.get_all(director_id=director_id)
        if not movies:
            return None

        plt.rcParams["font.family"] = CHART_FONT

        # DỮ LIỆU BIỂU ĐỒ
        # 1. Thống kê theo thời gian (Gộp doanh thu theo từng năm)
        year_revenue = {}
        year_count = {}
        for m in movies:
            if m.revenue:
                year_revenue[m.year] = year_revenue.get(m.year, 0) + m.revenue
            year_count[m.year] = year_count.get(m.year, 0) + 1

        sorted_years = sorted(year_revenue)
        revenues_by_year = [year_revenue[y] / 1_000_000 for y in sorted_years]

        sorted_count_years = sorted(year_count)
        counts_by_year = [year_count[y] for y in sorted_count_years]

        # 2. Top 5 phim
        top_5 = sorted(movies, key=lambda x: x.revenue or 0, reverse=True)[:5]
        labels_top5 = [
            (m.title[:18] + "...") if len(m.title) > 18 else m.title
            for m in top_5
        ]
        revs_top5 = [m.revenue / 1_000_000 for m in top_5]

        # 3. Doanh thu theo đạo diễn
        director_data = {}
        for m in movies:
            if not m.revenue:
                continue
            director = self.director_repo.get_by_id(m.director_id)
            d_name = director.name if director else "Unknown"
            short_name = d_name.split()[-1] if d_name != "Unknown" else "Unknown"
            director_data[short_name] = director_data.get(short_name, 0) + m.revenue

        top_directors = sorted(
            director_data.items(), key=lambda x: x[1], reverse=True
        )[:8]
        d_names = [item[0] for item in top_directors]
        d_revs  = [item[1] / 1_000_000 for item in top_directors]

        # 4. Phân bổ doanh thu
        all_revenues_b = [m.revenue / 1_000_000_000 for m in movies if m.revenue]

        # 5. Doanh thu trung bình theo thập kỷ
        decade_revenue = {}
        decade_count   = {}
        for m in movies:
            if not m.revenue:
                continue
            decade = (m.year // 10) * 10        # 2013 → 2010
            decade_revenue[decade] = decade_revenue.get(decade, 0) + m.revenue
            decade_count[decade]   = decade_count.get(decade, 0) + 1

        sorted_decades = sorted(decade_revenue)
        avg_by_decade  = [
            decade_revenue[d] / decade_count[d] / 1_000_000
            for d in sorted_decades
        ]
        decade_labels  = [f"{d}s" for d in sorted_decades]

        # VẼ BIỂU ĐỒ
        plt.style.use("ggplot")
        fig, axes = plt.subplots(3, 2, figsize=(14, 16))
        fig.patch.set_facecolor("#f8f9fa")
        ax1, ax2, ax3, ax4, ax5, ax6 = axes.flatten()
        
        # Biểu đồ 1: Xu hướng doanh thu theo năm (Line Chart)
        ax1.plot(
            sorted_years, revenues_by_year,
            marker="o", color="#28a745", linewidth=2.2, markersize=5,
        )
        ax1.fill_between(sorted_years, revenues_by_year, alpha=0.1, color="#28a745")
        ax1.set_title("Revenue Trend by Year", fontsize=13, pad=10, fontweight="bold")
        ax1.set_xlabel("Year")
        ax1.set_ylabel("Total Revenue (Million $)")
        ax1.grid(True, alpha=0.35)
        ax1.set_facecolor("#ffffff")

        # Biểu đồ 2: Top 5 phim doanh thu cao nhất (Bar Chart)
       bars2 = ax2.bar(labels_top5, revs_top5,
                        color=BAR_COLORS[:len(top_5)], width=0.55)
        for bar, val in zip(bars2, revs_top5):
            ax2.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(revs_top5) * 0.01,
                f"${val:,.0f}M",
                ha="center", va="bottom", fontsize=8, fontweight="bold",
            )
        ax2.set_title("Top 5 Movies by Revenue", fontsize=13, pad=10, fontweight="bold")
        ax2.set_ylabel("Revenue (Million $)")
        ax2.set_facecolor("#ffffff")
        ax2.tick_params(axis="x", labelsize=8)

        # Biểu đồ 3: Bar chart doanh thu theo đạo diễn
        bars3 = ax3.bar(d_names, d_revs,
                        color=BAR_COLORS[:len(d_names)], width=0.6)
        for bar, val in zip(bars3, d_revs):
            ax3.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(d_revs) * 0.01,
                f"${val:,.0f}M",
                ha="center", va="bottom", fontsize=8, fontweight="bold",
            )
        ax3.set_title("Top Directors by Total Revenue",
                      fontsize=13, pad=10, fontweight="bold")
        ax3.set_ylabel("Total Revenue (Million $)")
        ax3.set_facecolor("#ffffff")
        ax3.tick_params(axis="x", labelsize=8)

        # Biểu đồ 4: Bar chart số lượng phim theo năm
        ax4.bar(sorted_count_years, counts_by_year,
                color="#17a2b8", width=0.7, alpha=0.85)
        ax4.set_title("Number of Movies Released per Year",
                      fontsize=13, pad=10, fontweight="bold")
        ax4.set_xlabel("Year")
        ax4.set_ylabel("Number of Movies")
        ax4.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
        ax4.set_facecolor("#ffffff")
        ax4.grid(axis="y", alpha=0.35)

        # Biểu đồ 5: Histogram phân bố doanh thu
        ax5.hist(all_revenues_b, bins=10, color="#fd7e14",
                 edgecolor="white", alpha=0.9)
        ax5.set_title("Revenue Distribution (Billion $)",
                      fontsize=13, pad=10, fontweight="bold")
        ax5.set_xlabel("Revenue (Billion $)")
        ax5.set_ylabel("Number of Movies")
        ax5.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
        ax5.set_facecolor("#ffffff")
        ax5.grid(axis="y", alpha=0.35)

        # Biểu đồ 6: Bar chart doanh thu trung bình theo thập kỷ
        bars6 = ax6.bar(decade_labels, avg_by_decade,
                        color=BAR_COLORS[:len(decade_labels)], width=0.5)
        for bar, val in zip(bars6, avg_by_decade):
            ax6.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(avg_by_decade) * 0.01,
                f"${val:,.0f}M",
                ha="center", va="bottom", fontsize=9, fontweight="bold",
            )
        ax6.set_title("Avg Revenue by Decade",
                      fontsize=13, pad=10, fontweight="bold")
        ax6.set_ylabel("Avg Revenue (Million $)")
        ax6.set_facecolor("#ffffff")
        ax6.tick_params(axis="x", labelsize=10)

        plt.tight_layout(pad=3.0)
        
        # Chuyển đổi sang Base64 để hiển thị trên Web
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=110)
        buf.seek(0)
        chart_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close()
        
        return chart_base64

    def export_chart_png(self, file_path: str, director_id=None) -> bool:
        """Lưu biểu đồ ra file PNG"""
        try:
            chart_b64 = self.generate_charts(director_id=director_id)
            if not chart_b64:
                return False
            img_bytes = base64.b64decode(chart_b64)
            with open(file_path, "wb") as f:
                f.write(img_bytes)
            return True
        except Exception as e:
            print(f"[ERROR] Xuat PNG that bai: {e}")
            return False
