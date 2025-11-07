from flask import Flask, render_template, request, session, redirect, url_for
import base64
import os
import io

from datetime import timedelta
# 引入原始腳本中的函式
import sys
from urllib.parse import urljoin, urlparse
import time
from PIL import Image, ImageDraw, ImageFont
import textwrap
from scraper import Scraper
import re # 將 re 模組的導入移到檔案頂部
from config import LAYOUT_CONFIG
from functools import wraps

# 取得目前檔案所在的目錄
APP_ROOT = os.path.dirname(os.path.abspath(__file__))

def get_font(size, bold=False):
    """獲取思源黑體字體"""
    # 根據 bold 參數從 config 讀取對應的字體檔案名稱
    if bold and LAYOUT_CONFIG['title'].get('font_path_bold'):
        font_filename = LAYOUT_CONFIG['title']['font_path_bold']
    else:
        # 假設有一個常規字體的設定，如果沒有，則使用一個預設值
        font_filename = LAYOUT_CONFIG['title'].get('font_path_regular', 'NotoSansTC-Regular.ttf')

    font_path = os.path.join(APP_ROOT, 'static', font_filename)
    try:
        return ImageFont.truetype(font_path, size)
    except IOError:
        print(f"警告: 無法在 '{font_path}' 找到字體檔案，將使用預設字體。")
        return ImageFont.load_default()

def wrap_text(text, font, max_width):
    """文字換行處理"""
    lines = []
    words = list(text)
    current_line = ""
    
    for word in words:
        test_line = current_line + word
        bbox = font.getbbox(test_line)
        width = bbox[2] - bbox[0]
        
        if width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    return lines

def create_layout_image(data, show_source=True, dual_image_data=None):
    """創建自動排版圖片"""
    
    # 從設定檔讀取參數
    cfg = LAYOUT_CONFIG
    
    try:
        # 假設背景圖片也放在 'static' 資料夾中
        background_path = os.path.join(APP_ROOT, 'static', cfg['layout']['background_path'])
        background = Image.open(background_path)
        
        if background.size != (cfg['layout']['width'], cfg['layout']['height']):
            background = background.resize((cfg['layout']['width'], cfg['layout']['height']), Image.Resampling.LANCZOS)
            
    except FileNotFoundError:
        background = Image.new('RGB', (cfg['layout']['width'], cfg['layout']['height']), color='white')
        print(f"警告: 找不到背景圖片 {background_path}，已使用白色背景替代。")
    except Exception as e:
        return None
    
    draw = ImageDraw.Draw(background)
    
    # 版面區域變數
    start_x = cfg['layout']['white_area_left']
    current_y = cfg['layout']['white_area_top']
    white_area_width = cfg['layout']['white_area_width']
    white_area_height = cfg['layout']['white_area_height']
    header_height = cfg['layout']['header_height']
    
    # 1. 繪製標題區域
    title_cfg = cfg['title']
    title_font = get_font(title_cfg['base_font_size'], bold=False)
    title_text = data.get('title', '未找到標題')

    # 先用基本字體計算分行，以判斷是單行還是多行
    title_lines_initial_wrap = wrap_text(title_text, title_font, white_area_width - title_cfg['horizontal_padding']) 

    # 計算標題文字在其預留區域內的可用垂直空間
    available_title_content_height = header_height

    if len(title_lines_initial_wrap) == 1:
        s_cfg = title_cfg['single_line']
        single_line_text = title_lines_initial_wrap[0]
        
        # 獲取初始字體大小下的文字尺寸
        initial_font_bbox = title_font.getbbox(single_line_text)
        current_text_width_at_initial_size = initial_font_bbox[2] - initial_font_bbox[0]

        available_horizontal_space = white_area_width - title_cfg['horizontal_padding']

        final_font_size_for_single_line = title_cfg['base_font_size']
        
        # 如果單行文字在初始字體大小下太短，則嘗試放大字體
        if current_text_width_at_initial_size < available_horizontal_space * s_cfg['fill_percentage']:
            # 計算需要的縮放因子
            scale_factor = (available_horizontal_space * s_cfg['fill_percentage']) / current_text_width_at_initial_size
            final_font_size_for_single_line = min(int(title_cfg['base_font_size'] * scale_factor), title_cfg['max_font_size'])
        
        # 獲取最終用於繪製的字體（可能已放大）
        actual_drawing_font = get_font(final_font_size_for_single_line, bold=False)
        
        # 重新計算原始文字的寬高，使用調整後的字體大小
        text_bbox = actual_drawing_font.getbbox(single_line_text)
        original_text_width = text_bbox[2] - text_bbox[0]
        original_text_height = text_bbox[3] - text_bbox[1]
        
        if original_text_height > 0:
            target_stretched_content_height = int(original_text_height * s_cfg['vertical_stretch_factor'])
            max_allowed_stretched_height = available_title_content_height * s_cfg['max_stretch_factor']
            target_stretched_content_height = min(target_stretched_content_height, int(max_allowed_stretched_height))

            padding_h = s_cfg['temp_image_padding_h']
            padding_v = s_cfg['temp_image_padding_v']

            temp_img = Image.new('RGBA', 
                                     (original_text_width + padding_h, 
                                      original_text_height + padding_v), 
                                     (255, 255, 255, 0))
            temp_draw = ImageDraw.Draw(temp_img)
            
            temp_draw.text((padding_h // 2, padding_v // 2), single_line_text, font=actual_drawing_font, fill='black')

            new_scaled_height_of_temp_img = int(target_stretched_content_height + padding_v)
            scaled_img_width = temp_img.width 
            
            scaled_img = temp_img.resize((scaled_img_width, new_scaled_height_of_temp_img), Image.Resampling.LANCZOS)
            
            paste_x = start_x + (white_area_width - scaled_img.width) // 2
            paste_y = (current_y + s_cfg['vertical_offset']) + (available_title_content_height - scaled_img.height) // 2
            
            background.paste(scaled_img, (paste_x, paste_y), scaled_img) 
        else:
            text_x = start_x + (white_area_width - original_text_width) // 2
            text_y = (current_y + s_cfg['vertical_offset']) + (available_title_content_height - original_text_height) // 2 
            draw.text((text_x, text_y), single_line_text, font=actual_drawing_font, fill='black')
            
        current_y += header_height 

    else: # 多行標題的處理 (使用基本字體)
        title_y = current_y + title_cfg['vertical_offset_multiline']
        
        for line in title_lines_initial_wrap[:2]: # 僅顯示前兩行
            text_x = start_x + (title_cfg['horizontal_padding'] / 2)
            draw.text((text_x, title_y), line, font=title_font, fill='black')
            title_y += title_cfg['base_font_size'] * title_cfg['line_height_multiplier']
        
        current_y += header_height 
    
    # 2. 計算內容實際需要的高度
    content_cfg = cfg['content']
    content_font = get_font(content_cfg['font_size'])
    content_text = data.get('content', '未找到內容')
    content_lines = wrap_text(content_text, content_font, white_area_width - title_cfg['horizontal_padding'])
    
    content_actual_height = content_cfg['top_padding'] + (len(content_lines) * content_cfg['line_height']) + content_cfg['bottom_padding']
    
    # 3. 繪製內容區域（動態高度）
    content_y = current_y + content_cfg['top_padding']
    
    for line in content_lines:
        draw.text((start_x + (title_cfg['horizontal_padding'] / 2), content_y), line, font=content_font, fill='black')
        content_y += content_cfg['line_height']
    
    current_y += content_actual_height
    
    # 4. 添加間距
    current_y += cfg['layout']['content_image_gap']
    
    # 5. 計算圖片區域高度（剩餘空間）
    image_cfg = cfg['image']
    remaining_height = cfg['layout']['white_area_top'] + white_area_height - current_y
    image_height = max(image_cfg['min_height'], remaining_height)
    
    # 如果計算出的高度太小，調整佈局
    if image_height < image_cfg['min_height_for_full_content']:
        max_content_lines = min(len(content_lines), content_cfg['max_lines_when_cramped'])
        content_actual_height = content_cfg['top_padding'] + (max_content_lines * content_cfg['line_height']) + content_cfg['bottom_padding']
        
        draw.rectangle([start_x, cfg['layout']['white_area_top'] + header_height, start_x + white_area_width, cfg['layout']['white_area_top'] + white_area_height], fill='white')
        
        current_y = cfg['layout']['white_area_top'] + header_height
        content_y = current_y + content_cfg['top_padding']
        
        for line in content_lines[:max_content_lines]:
            draw.text((start_x + (title_cfg['horizontal_padding'] / 2), content_y), line, font=content_font, fill='black')
            content_y += content_cfg['line_height']
        
        if len(content_lines) > max_content_lines:
            draw.text((start_x + (title_cfg['horizontal_padding'] / 2), content_y), "...", font=content_font, fill='black')
        
        current_y += content_actual_height + cfg['layout']['content_image_gap']
        image_height = cfg['layout']['white_area_top'] + white_area_height - current_y
    
    # 6. 繪製圖片區域（動態高度）
    # <<<< 修正：雙框圖片邏輯 >>>>
    if dual_image_data:
        img1_url = dual_image_data.get('img1_url')
        img2_url = dual_image_data.get('img2_url')
        img1_idx = dual_image_data.get('img1_idx')
        img2_idx = dual_image_data.get('img2_idx')
    
        img1 = Scraper.download_image(img1_url) if img1_url else None
        img2 = Scraper.download_image(img2_url) if img2_url else None
    
        # 計算每張圖片的寬度和間距
        gap = image_cfg['dual_image_gap']
        img_width = (white_area_width - gap) // 2
        img_height = image_height
    
        # 貼上第一張圖
        if img1:
            img1_resized = img1.resize((img_width, img_height), Image.Resampling.LANCZOS)
            background.paste(img1_resized, (start_x, current_y))
        else:
            draw.rectangle([start_x, current_y, start_x + img_width, current_y + img_height], fill='grey')
            draw.text((start_x + 20, current_y + 20), f"圖 {img1_idx} 載入失敗", font=get_font(24), fill='white')
    
        # 貼上第二張圖
        if img2:
            img2_resized = img2.resize((img_width, img_height), Image.Resampling.LANCZOS)
            background.paste(img2_resized, (start_x + img_width + gap, current_y))
        else:
            draw.rectangle([start_x + img_width + gap, current_y, start_x + white_area_width, current_y + img_height], fill='grey')
            draw.text((start_x + img_width + gap + 20, current_y + 20), f"圖 {img2_idx} 載入失敗", font=get_font(24), fill='white')
    
        # <<<< 修正：只有勾選「含資料來源」時才繪製文字 >>>>
        if show_source:
            # 優先使用第一張圖的 alt_text，如果不存在則使用 "圖X跟圖X" 作為備用
            source_text = dual_image_data.get('alt_text')
            if not source_text or source_text in ['無替代文字', '未找到圖片或無替代文字']:
                source_text = f"圖{img1_idx}跟圖{img2_idx}"
            
            try:
                alt_font = ImageFont.truetype(image_cfg['source_text_font_path'], image_cfg['source_text_font_size'])
            except Exception:
                alt_font = get_font(image_cfg['source_text_font_size'])
            
            bbox = alt_font.getbbox(source_text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            alt_x = start_x + white_area_width - text_width - image_cfg['source_text_horizontal_margin']
            alt_y = current_y + image_height - text_height - image_cfg['source_text_vertical_margin']
            
            # 繪製黑色描邊
            stroke_width = image_cfg['source_text_stroke_width']
            for x_offset in range(-stroke_width, stroke_width + 1):
                for y_offset in range(-stroke_width, stroke_width + 1):
                    if x_offset != 0 or y_offset != 0: 
                        draw.text((alt_x + x_offset, alt_y + y_offset), source_text, font=alt_font, fill='black')
            
            # 繪製白色文字
            draw.text((alt_x, alt_y), source_text, font=alt_font, fill='white')

    # <<<< 原本的單張圖片邏輯 >>>>
    else:
        image_url = data.get('image_url', '')
        if image_url and image_url != '未找到圖片':
            downloaded_image = Scraper.download_image(image_url)
            
            if downloaded_image: # 圖片已成功下載
                target_width = white_area_width
                target_height = image_height
                
                resized_image = downloaded_image.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                paste_x = start_x
                paste_y = current_y
                
                background.paste(resized_image, (paste_x, paste_y))
                
                alt_text = data.get('alt_text', '')
                # 只有當「顯示資料來源」被勾選，且有實際的 alt_text 時才繪製
                if show_source and alt_text and alt_text != '未找到圖片或無替代文字':
                    try:
                        # 假設來源字體也放在 'static' 資料夾
                        source_font_path = os.path.join(APP_ROOT, 'static', image_cfg['source_text_font_path'])
                        alt_font = ImageFont.truetype(source_font_path, image_cfg['source_text_font_size'])
                    except (OSError, IOError, ValueError) as e:
                        print(f"警告：無法載入指定的來源字體 {source_font_path}，將使用預設字體。錯誤：{e}")
                        alt_font = get_font(image_cfg['source_text_font_size']) # 使用預設的 get_font
                    
                    bbox = alt_font.getbbox(alt_text)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    
                    alt_x = start_x + white_area_width - text_width - image_cfg['source_text_horizontal_margin']
                    alt_y = current_y + image_height - text_height - image_cfg['source_text_vertical_margin']
                    
                    stroke_width = image_cfg['source_text_stroke_width']
                    for x_offset in range(-stroke_width, stroke_width + 1):
                        for y_offset in range(-stroke_width, stroke_width + 1):
                            if x_offset != 0 or y_offset != 0: 
                                draw.text((alt_x + x_offset, alt_y + y_offset), alt_text, font=alt_font, fill='black')

                    draw.text((alt_x, alt_y), alt_text, font=alt_font, fill='white')
            else: # 圖片下載失敗
                error_font = get_font(32)
                error_text = "圖片載入失敗"
                bbox = error_font.getbbox(error_text)
                text_width = bbox[2] - bbox[0]
                text_x = start_x + (white_area_width - text_width) // 2
                text_y = current_y + image_height // 2 - 20
                draw.text((text_x, text_y), error_text, font=error_font, fill='white')
        else: # 沒有圖片URL或圖片URL無效
            no_image_font = get_font(32)
            no_image_text = "無圖片內容"
            bbox = no_image_font.getbbox(no_image_text)
            text_width = bbox[2] - bbox[0]
            text_x = start_x + (white_area_width - text_width) // 2
            text_y = current_y + image_height // 2 - 20
            draw.text((text_x, text_y), no_image_text, font=no_image_font, fill='white')
    
    return background

# --- Flask 應用程式設定 ---

app = Flask(__name__)

# --- 密碼與 Session 設定 ---
# 為了讓 session 運作，需要設定一個 secret_key
# 在生產環境中，建議使用更複雜且來自環境變數的密鑰
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a_default_secret_key_for_development')

# 從環境變數讀取密碼，如果沒有設定，則使用一個預設密碼
APP_PASSWORD = os.environ.get('APP_PASSWORD', 'ctinews')

# 設定 session 的有效期限為 30 分鐘
app.permanent_session_lifetime = timedelta(minutes=30)


# --- 簡單的記憶體快取機制 ---
url_cache = {}
CACHE_TTL = 600  # 快取存活時間（秒），這裡設定為 10 分鐘

# --- 登入裝飾器 ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def make_session_permanent():
    # 在每個請求前，將 session 設為永久性，這樣才會套用 lifetime 設定
    # 並且每次使用者有操作時，session 的到期時間會被自動刷新
    session.permanent = True

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == APP_PASSWORD:
            session['logged_in'] = True
            next_url = request.args.get('next')
            return redirect(next_url or url_for('index'))
        else:
            error = '密碼錯誤，請重試。'
    return render_template('login.html', error=error)

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('logged_in', None)
    # 如果是 GET 請求 (手動點擊按鈕)，則重導向；如果是 POST (來自 sendBeacon)，則回傳空的回應即可
    return redirect(url_for('login')) if request.method == 'GET' else ('', 204)

@app.route('/')
@login_required
def index():
    """首頁路由，顯示網址輸入表單"""
    return render_template('index.html')

@app.route('/generate_image', methods=['GET', 'POST'])
@login_required
def generate_image():
    if request.method == 'GET':
        return redirect(url_for('index'))

    url = request.form.get('url')
    if not url:
        return render_template('index.html', error="請輸入有效的網址。")

    try:
        # 檢查新功能選項
        is_dual_image = request.form.get('dual_image') == 'on'
        show_source = request.form.get('show_source') == 'on'
        
        # 檢查是否有編輯過的文字傳入
        edited_title = request.form.get('edited_title')
        edited_content = request.form.get('edited_content')
        edited_alt_text = request.form.get('edited_alt_text')

        # --- 全新的、更穩定的快取邏輯 ---
        # 我們將 soup 物件直接存在 session 中，避免因伺服器程序重啟導致快取遺失
        # 只有在第一次請求或 URL 變更時才執行爬取
        if 'last_url' not in session or session['last_url'] != url or not session.get('soup_cache'):
            print(f"SESSION CACHE MISS for URL: {url}")
            scraper = Scraper(url)
            # 將 soup 物件轉換為字串存入 session
            session['soup_cache'] = str(scraper.soup)
            session['last_url'] = url
        else:
            print(f"SESSION CACHE HIT for URL: {url}")
            # 從 session 中讀取 soup 字串並重新解析
            from bs4 import BeautifulSoup
            cached_soup = BeautifulSoup(session['soup_cache'], 'html.parser')
            scraper = Scraper(url, soup=cached_soup)

        dual_image_data = None
        layout_image = None

        # --- 核心邏輯切換 ---
        if is_dual_image:
            # 雙框圖片模式
            try:
                img1_idx = int(request.form.get('image_index_1', 1))
                img2_idx = int(request.form.get('image_index_2', 2))
            except (ValueError, TypeError):
                return render_template('index.html', error="圖片索引必須是數字。")

            all_images = scraper.get_all_content_images()
            if len(all_images) < max(img1_idx, img2_idx):
                return render_template('index.html', error=f"文章圖片數量不足 (共 {len(all_images)} 張)，無法選取第 {max(img1_idx, img2_idx)} 張圖。")

            # 準備傳給繪圖函式的資料
            title = edited_title if edited_title is not None else scraper.extract_title()
            content = edited_content if edited_content is not None else scraper.extract_first_content()
            dual_image_data = {
                'title': title, # 直接使用從 soup 提取的資料
                'content': content,
                'img1_url': all_images[img1_idx - 1]['image_url'],
                'alt_text': edited_alt_text if edited_alt_text is not None else all_images[img1_idx - 1]['alt_text'],
                'img2_url': all_images[img2_idx - 1]['image_url'],
                'img1_idx': img1_idx,
                'img2_idx': img2_idx,
            }
            # 將 dual_image_data 同時指派給 result，以供後續程式碼使用
            result = dual_image_data
            layout_image = create_layout_image(dual_image_data, show_source=show_source, dual_image_data=dual_image_data)

        else:
            # 原本的單張圖片模式
            if edited_title is not None or edited_content is not None or edited_alt_text is not None:
                # 如果是重新生成，使用編輯過的文字
                original_data = scraper.get_content() # 仍然需要圖片URL
                result = {
                    'title': edited_title if edited_title is not None else original_data['title'],
                    'content': edited_content if edited_content is not None else original_data['content'],
                    'image_url': original_data['image_url'],
                    'alt_text': edited_alt_text if edited_alt_text is not None else original_data['alt_text']
                }
            else:
                # 第一次生成
                result = scraper.get_content()
            layout_image = create_layout_image(result, show_source=show_source)

        if 'error' in result:
            return render_template('index.html', error=result['error'])

        if layout_image is None:
            return render_template('index.html', error="圖片創建失敗，請檢查底圖或字體檔案。")

        # 將最終圖片轉換為 base64
        img_byte_arr = io.BytesIO()
        layout_image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        image_data_uri = "data:image/png;base64," + base64.b64encode(img_byte_arr.read()).decode('ascii')

        return render_template(
            'index.html',
            image_data_uri=image_data_uri,
            title=result['title'],
            content_snippet=result['content'],
            alt_text=result['alt_text']
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return render_template('index.html', error=f"處理失敗: {str(e)}")

@app.route('/debug_html', methods=['POST'])
@login_required
def debug_html():
    """診斷網頁 HTML 結構的路由"""
    url = request.form.get('url') # 新增：從表單中獲取 URL
    if not url:
        return "請提供 URL"
    
    try:
        scraper = Scraper(url) # 現在 url 變數已定義
        debug_info = []
        debug_info.append("=== HTML 結構診斷 ===\n")
        
        # 1. 檢查所有 img 標籤
        all_imgs = scraper.soup.find_all('img')
        debug_info.append(f"1. 整個頁面的 <img> 標籤總數: {len(all_imgs)}\n")
        for idx, img in enumerate(all_imgs[:10], 1):
            src = Scraper._get_image_src(img) # 修正：應使用 Scraper 類別的方法
            alt = img.get('alt', '(無)')
            debug_info.append(f"   圖片 {idx}:")
            debug_info.append(f"     src: {src[:100] if src else '(無)'}")
            debug_info.append(f"     alt: {alt[:50]}\n")
        
        # 2. 檢查 article 標籤
        article = scraper.soup.find('article')
        if article:
            article_imgs = article.find_all('img')
            debug_info.append(f"\n2. <article> 標籤內的圖片數: {len(article_imgs)}")
            debug_info.append(f"   <article> 的 class: {article.get('class', '(無)')}")
        else:
            debug_info.append("\n2. 未找到 <article> 標籤\n")
        
        # 3. 查找所有包含 ctinews 圖片 URL 的文字
        debug_info.append("\n3. 搜尋頁面原始碼中是否包含圖片 URL:")
        if 'storage.ctinews.com/compression/files/default/cut-' in scraper.soup.prettify():
            # import re # 這裡的 import re 可以移除，因為檔案頂部已導入
            debug_info.append("   ✓ 找到 storage.ctinews.com 圖片 URL\n")
            # 提取圖片 URL
            urls = re.findall(r'https?://storage\.ctinews\.com[^"\s]+\.jpg', scraper.soup.prettify())
            debug_info.append(f"   找到 {len(urls)} 個圖片 URL:")
            for url in urls[:5]:
                debug_info.append(f"   - {url}")
        else:
            debug_info.append("   ✗ 未找到 storage.ctinews.com 圖片 URL\n")
        
        return '<pre>' + '\n'.join(debug_info) + '</pre>'
        
    except Exception as e:
        import traceback
        return f"<pre>錯誤: {str(e)}\n\n{traceback.format_exc()}</pre>"

if __name__ == '__main__':
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("❌ 缺少 Pillow 套件，請執行: pip install Pillow")
        sys.exit(1)
    
    # 部署時，會由 Gunicorn 等 WSGI 伺服器啟動，而不是直接執行 app.run()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)
