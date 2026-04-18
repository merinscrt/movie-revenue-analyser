import matplotlib
matplotlib.use('Agg') # Ngăn lỗi 'main thread is not in main loop' trên Flask
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import io
import base64
from repositories.movie_repo import MovieRepository

def _get_vietnamese_font():
    preferred = [
        "Arial", "Segoe UI", "Tahoma",         
        "DejaVu Sans",                           
        "Helvetica Neue", "Helvetica",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for font in preferred:
        if font in available:
            return font
    return "DejaVu Sans"

CHART_FONT = _get_vietnamese_font()

class AnalysisService:
    def __init__(self):
        self.movie_repo = MovieRepository()

    def get_statistics(self, search_query=None, sort_by=None, director_id=None):
        movies = self.movie_repo.get_all(search_query=search_query, sort_by=sort_by, director_id=director_id)
        if not movies:
            return {"count": 0, "total_revenue": 0, "avg_revenue": 0, "top_movies": []}
            
        total_rev = sum(m.revenue for m in movies if m.revenue)
        avg_rev = total_rev / len(movies)
        # Sắp xếp theo doanh thu giảm dần để lấy Top 5
        top_movies = sorted(movies, key=lambda x: x.revenue or 0, reverse=True)[:5]
        
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

        # 1. Thống kê theo thời gian (Gộp doanh thu theo từng năm)
        year_data: dict[int, float] = {}
        for m in movies:
            if m.revenue:
                year_data[m.year] = year_data.get(m.year, 0) + m.revenue
        
        sorted_years = sorted(year_data)
        total_revenues_m = [year_data[y] / 1_000_000 for y in sorted_years] # Đơn vị: Triệu USD

        # 2. Top 5 phim
        top_5 = sorted(movies, key=lambda x: x.revenue or 0, reverse=True)[:5]
        labels = [
            (m.title[:18] + "…") if len(m.title) > 18 else m.title
            for m in top_5
        ]
        top_revs = [m.revenue / 1_000_000 for m in top_5]
        bar_colors = ["#ffc107", "#17a2b8", "#dc3545", "#007bff", "#6610f2"]

        # 3. Chuẩn bị vẽ 2 biểu đồ (Subplots)
        plt.style.use('ggplot')
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 10))
        fig.patch.set_facecolor("#f8f9fa")
        
        # Biểu đồ 1: Xu hướng doanh thu theo năm (Line Chart)
        ax1.plot(sorted_years, total_revenues_m, marker='o', color='#28a745', linewidth=2.2, markersize=5)
        ax1.fill_between(sorted_years, total_revenues_m, alpha=0.1, color="#28a745")
        ax1.set_title('Xu hướng Tổng doanh thu theo Năm', fontsize=14, pad=12, fontweight="bold")
        ax1.set_xlabel('Năm')
        ax1.set_ylabel('Tổng doanh thu (Triệu $)')
        ax1.grid(True, alpha=0.3)
        ax1.set_facecolor("#ffffff")

        # Biểu đồ 2: Top 5 phim doanh thu cao nhất (Bar Chart)
        bars = ax2.bar(labels, top_revs, color=bar_colors[:len(top_5)], width=0.55)
        for bar, val in zip(bars, top_revs):
            ax2.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(top_revs) * 0.01,
                f"${val:,.0f}M",
                ha="center", va="bottom", fontsize=9, fontweight="bold",
            )
        ax2.set_title("Top 5 Phim có Doanh thu cao nhất", fontsize=14, pad=12, fontweight="bold")
        ax2.set_ylabel("Doanh thu (Triệu $)")
        ax2.set_facecolor("#ffffff")
        ax2.tick_params(axis="x", labelsize=9)

        plt.tight_layout(pad=2.5)
        
        # Chuyển đổi sang Base64 để hiển thị trên Web
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=110)
        buf.seek(0)
        chart_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close(fig)
        
        return chart_base64
