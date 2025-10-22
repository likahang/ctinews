"""
這個檔案集中管理圖片生成的所有版面設計參數。
修改此處的數值可以直接影響最終生成圖片的樣式，而無需更動 app.py 中的核心邏輯。
"""

LAYOUT_CONFIG = {
    # --- 整體版面配置 ---
    "layout": {
        "width": 1920,
        "height": 1080,
        "background_path": "ctinews_background.jpg", # 建議改為英文檔名
        "white_area_left": 35,
        "white_area_top": 142,
        "white_area_width": 1850,
        "white_area_height": 960,
        "header_height": 171,
        "content_image_gap": 10,  # 內文與圖片之間的間距
    },

    # --- 標題區域設定 ---
    "title": {
        "font_path_regular": "NotoSansTC-Regular.ttf", # 常規字體路徑
        "font_path_bold": "NotoSansTC-Bold.ttf", # 粗體字體路徑 (如果需要)
        "base_font_size": 82,
        "max_font_size": 120,
        "line_height_multiplier": 1.1, # 多行標題的行高乘數 (相對於字體大小)
        "horizontal_padding": 40,
        "vertical_padding_multiline": 20,
        "vertical_offset_multiline": -20, # 多行標題的垂直微調
        # 單行標題放大與拉伸設定
        "single_line": {
            "fill_percentage": 1.0,
            "vertical_stretch_factor": 2.00,
            "max_stretch_factor": 2.0,
            "temp_image_padding_h": 40,
            "temp_image_padding_v": 60,
            "vertical_offset": -50, # 單行標題的垂直微調
        }
    },

    # --- 內文區域設定 ---
    "content": {
        "font_size": 28,
        "line_height": 35,
        "top_padding": 5,
        "bottom_padding": 15,
        "max_lines_when_cramped": 8, # 當圖片空間不足時，內文最多顯示的行數
    },

    # --- 圖片與來源文字設定 ---
    "image": {
        "min_height": 200,
        "min_height_for_full_content": 300,
        "dual_image_gap": 10, # 雙框圖片之間的間距
        "source_text_font_path": "DFT_8.TTC",
        "source_text_font_size": 36,
        "source_text_horizontal_margin": 30,
        "source_text_vertical_margin": 60,
        "source_text_stroke_width": 3,
    }
}