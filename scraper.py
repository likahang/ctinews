import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import urllib3
import warnings
import re
import io
from PIL import Image

# 忽略SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)

class Scraper:
    """
    一個封裝了網頁內容抓取和解析邏輯的類別。
    """
    def __init__(self, url, soup=None):
        self.url = self._validate_url(url)
        self.base_url = f"{urlparse(self.url).scheme}://{urlparse(self.url).netloc}"
        if soup:
            self.soup = soup
        else:
            self.soup = self._get_soup()

    def _validate_url(self, url):
        """驗證網址格式，如果沒有 scheme 則自動加上 https://"""
        parsed = urlparse(url)
        if not parsed.scheme:
            return 'https://' + url
        return url

    def _get_soup(self):
        """發送請求並獲取 BeautifulSoup 物件"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
        }
        response = requests.get(self.url, headers=headers, verify=False, timeout=20, allow_redirects=True)
        response.raise_for_status()
        return BeautifulSoup(response.content.decode('utf-8', 'ignore'), 'html.parser')

    def get_content(self):
        """提取網頁主要內容（標題、內文、主圖）"""
        if not self.soup:
            raise ConnectionError("無法獲取網頁內容")
            
        title = self.extract_title()
        content = self.extract_first_content()
        image_data = self.extract_main_article_image()
        
        return {
            'title': title,
            'content': content,
            'image_url': image_data['image_url'],
            'alt_text': image_data['alt_text']
        }

    def extract_title(self):
        """提取標題"""
        h1_tags = self.soup.find_all('h1')
        for h1 in h1_tags:
            text = h1.get_text().strip()
            if text and len(text) > 5:
                return text
        
        title_tag = self.soup.find('title')
        if title_tag:
            text = title_tag.get_text().strip()
            return text.split('|')[0].strip()
        
        return '未找到標題'

    def extract_first_content(self):
        """提取第一段內容"""
        paragraphs = self.soup.find_all('p')
        for p in paragraphs:
            text = p.get_text().strip()
            if text and len(text) > 50:
                return text
        return '未找到內容段落'

    def extract_main_article_image(self):
        """提取文章主要配圖"""
        main_image = self._find_first_content_image()
        if main_image: return main_image
        
        main_image = self._find_by_image_characteristics()
        if main_image: return main_image
        
        main_image = self._find_by_improved_scoring()
        if main_image: return main_image
        
        return {'image_url': '未找到圖片', 'alt_text': '未找到圖片或無替代文字'}

    def get_all_content_images(self):
        """提取文章內文中所有有意義的圖片"""
        content_selectors = [
            'article', '.article-content', '.content', '.post-content', 
            '.entry-content', '[class*="content"]', 'main', 'body'
        ]
        content_area = self.soup
        for selector in content_selectors:
            area = self.soup.select_one(selector)
            if area and area.find_all('img'):
                content_area = area
                break
        
        images = content_area.find_all('img')
        found_images = []
        
        for img in images:
            src = self._get_image_src(img)
            if not src: continue

            if not src.startswith(('http://', 'https://')):
                src = urljoin(self.base_url, src)

            alt = self._get_image_alt_text(img)
            
            if self._is_content_image(src, alt):
                if not any(d['image_url'] == src for d in found_images):
                    clean_alt = self._clean_alt_text(alt)
                    found_images.append({'image_url': src, 'alt_text': clean_alt})
        
        if not found_images and images:
            for img in images:
                src = self._get_image_src(img)
                if not src: continue
                if not src.startswith(('http://', 'https://')):
                    src = urljoin(self.base_url, src)
                if 'storage.ctinews.com' in src or 'ctinews.com' in src:
                    alt = self._get_image_alt_text(img)
                    clean_alt = self._clean_alt_text(alt)
                    if not any(d['image_url'] == src for d in found_images):
                        found_images.append({'image_url': src, 'alt_text': clean_alt})
        
        return found_images

    # --- Helper Methods (Private) ---

    def _find_first_content_image(self):
        """方法1：找到文章內容區域的第一張有意義圖片，優先選擇標題附近或文章開頭的圖片"""
        content_selectors = [
            'article', '.article-content', '.content', '.post-content',
            '.entry-content', '[class*="content"]', 'main'
        ]
        content_area = self.soup.find('body') or self.soup
        for selector in content_selectors:
            area = self.soup.select_one(selector)
            if area:
                content_area = area
                break
        
        # 找到標題元素（h1 或標題相關的元素）
        title_element = None
        for tag in ['h1', 'h2', '.title', '[class*="title"]', '[class*="headline"]']:
            title_element = content_area.select_one(tag)
            if title_element:
                break
        
        # 收集所有候選圖片，並根據位置和特徵排序
        candidates = []
        all_elements = list(content_area.descendants)
        
        for img in content_area.find_all('img'):
            src = self._get_image_src(img)
            if not src: continue
            if not src.startswith(('http://', 'https://')):
                src = urljoin(self.base_url, src)
            
            alt = self._get_image_alt_text(img)
            if not self._is_content_image(src, alt):
                continue
            
            # 額外過濾：排除明顯不是主圖的圖片
            # 排除 SVG 格式的圖片（通常是圖標或裝飾，不是主圖）
            if src.startswith('data:image/svg+xml') or src.lower().endswith('.svg'):
                continue
            
            # 排除特定 URL 路徑的圖片（應用程式圖標、購物相關等）
            src_lower = src.lower()
            exclude_paths = ['/userapp/', '/app/', '/icon/', '/logo/', '/buy', '/shop', '/購物', '/shopping']
            if any(path in src_lower for path in exclude_paths):
                continue
            
            # 排除 URL 中包含特定關鍵字的圖片
            exclude_url_keywords = ['buy-ic', 'shop', 'cart', '購物', 'shopping', 'app-icon', 'userapp']
            if any(keyword in src_lower for keyword in exclude_url_keywords):
                continue
            
            # 排除尺寸過小的圖片（可能是圖標）
            width = img.get('width')
            height = img.get('height')
            if width and height:
                try:
                    w, h = int(width), int(height)
                    if w < 200 or h < 150:  # 太小的圖片跳過
                        continue
                except (ValueError, TypeError):
                    pass
            
            # 排除 alt 文字中包含特定關鍵字的圖片（可能是 logo、廣告、購物等）
            if alt:
                alt_lower = alt.lower()
                exclude_keywords = ['logo', 'icon', 'avatar', 'banner', 'ad', '廣告', '贊助', '快點購', '購物', 'shop', 'buy', '購買']
                if any(keyword in alt_lower for keyword in exclude_keywords):
                    continue
            
            # 計算優先級分數
            priority = 0
            img_index = -1
            
            # 獲取圖片在內容區域中的位置索引
            try:
                img_index = all_elements.index(img)
            except ValueError:
                pass
            
            # 優先選擇在標題附近的圖片
            if title_element:
                try:
                    title_index = all_elements.index(title_element)
                    if img_index > title_index and img_index - title_index < 50:  # 標題後50個元素內
                        priority += 100 - (img_index - title_index)  # 越近分數越高
                except ValueError:
                    pass
            
            # 優先選擇在文章開頭區域的圖片（前100個元素內）
            if img_index >= 0 and img_index < 100:
                priority += 50 - (img_index // 2)  # 越靠前分數越高
            
            # 優先選擇在 figure 標籤中的圖片
            if img.find_parent('figure'):
                priority += 30
            
            # 優先選擇有特定 class 或 data 屬性的圖片（可能是主圖標記）
            img_classes = img.get('class', [])
            if img_classes:
                class_str = ' '.join(img_classes).lower()
                if any(keyword in class_str for keyword in ['main', 'featured', 'hero', 'article', 'cover', 'headline']):
                    priority += 40
            
            # 優先選擇 storage.ctinews.com 的圖片
            if 'storage.ctinews.com' in src:
                priority += 20
                if '/compression/files/' in src:
                    priority += 10
            
            # 特別針對中天新聞網：優先選擇在文章正文第一段附近的圖片
            # 查找第一個段落（p 標籤），主圖通常在標題和第一段之間
            first_paragraph = content_area.find('p')
            if first_paragraph:
                try:
                    para_index = all_elements.index(first_paragraph)
                    # 如果圖片在標題和第一段之間，或緊接第一段之後，優先級很高
                    if title_element:
                        try:
                            title_index = all_elements.index(title_element)
                            if title_index < img_index <= para_index + 20:  # 標題後到第一段後20個元素內
                                priority += 80
                        except ValueError:
                            pass
                except ValueError:
                    pass
            
            # 優先選擇 alt 文字中包含「圖／」或「資料照」的圖片（中天新聞網的主圖特徵）
            if alt:
                if '圖／' in alt or '圖 /' in alt or '資料照' in alt:
                    priority += 60
                # 如果 alt 文字較長且包含中文，可能是主圖說明
                if len(alt) > 20 and re.search(r'[\u4e00-\u9fff]', alt):
                    priority += 20
            
            # 優先選擇尺寸較大的圖片（主圖通常較大）
            width = img.get('width')
            height = img.get('height')
            if width and height:
                try:
                    w, h = int(width), int(height)
                    if w >= 600 and h >= 400:  # 較大的圖片
                        priority += 30
                    elif w >= 400 and h >= 300:  # 中等大小的圖片
                        priority += 15
                except (ValueError, TypeError):
                    pass
            
            # 檢查圖片是否在特定的容器中（中天新聞網可能使用特定結構）
            parent = img.find_parent()
            if parent:
                parent_classes = parent.get('class', [])
                if parent_classes:
                    parent_class_str = ' '.join(parent_classes).lower()
                    # 如果圖片在文章內容相關的容器中
                    if any(keyword in parent_class_str for keyword in ['article', 'content', 'post', 'entry', 'main']):
                        priority += 25
            
            candidates.append({
                'image_url': src,
                'alt_text': self._clean_alt_text(alt),
                'priority': priority,
                'position': img_index
            })
        
        # 按優先級排序，優先級相同時按位置排序（越靠前越好）
        if candidates:
            candidates.sort(key=lambda x: (-x['priority'], x['position'] if x['position'] >= 0 else 999999))
            return {'image_url': candidates[0]['image_url'], 'alt_text': candidates[0]['alt_text']}
        
        return None

    def _find_by_image_characteristics(self):
        """方法2：根據圖片特徵判斷主圖"""
        candidates = []
        for img in self.soup.find_all('img'):
            src = self._get_image_src(img)
            alt = self._get_image_alt_text(img)
            if not src or not self._is_content_image(src, alt): continue
            if not src.startswith(('http://', 'https://')):
                src = urljoin(self.base_url, src)
            
            # 額外過濾：排除特定路徑和格式的圖片
            src_lower = src.lower()
            # 排除 SVG 圖片
            if src.startswith('data:image/svg+xml') or src_lower.endswith('.svg'):
                continue
            # 排除特定路徑
            if any(path in src_lower for path in ['/userapp/', '/app/', '/icon/', '/logo/', '/buy', '/shop', '/購物', '/shopping']):
                continue
            # 排除特定關鍵字
            if any(keyword in src_lower for keyword in ['buy-ic', 'shop', 'cart', '購物', 'shopping', 'app-icon', 'userapp']):
                continue
            # 排除 alt 文字中包含特定關鍵字
            if alt:
                alt_lower = alt.lower()
                if any(keyword in alt_lower for keyword in ['快點購', '購物', 'shop', 'buy', '購買']):
                    continue
            
            score = self._calculate_main_image_score(img, src, alt)
            candidates.append({'image_url': src, 'alt_text': self._clean_alt_text(alt), 'score': score})
        
        if candidates:
            best = max(candidates, key=lambda x: x['score'])
            return {'image_url': best['image_url'], 'alt_text': best['alt_text']}
        return None

    def _find_by_improved_scoring(self):
        """方法3：使用改進的評分系統"""
        best_image, best_score = None, -999
        for img in self.soup.find_all('img'):
            src = self._get_image_src(img)
            if not src: continue
            if not src.startswith(('http://', 'https://')):
                src = urljoin(self.base_url, src)
            
            # 過濾：排除明顯不是主圖的圖片
            if not self._is_content_image(src, ''):
                continue
            
            # 額外過濾：排除特定路徑和格式的圖片
            src_lower = src.lower()
            # 排除 SVG 圖片
            if src.startswith('data:image/svg+xml') or src_lower.endswith('.svg'):
                continue
            # 排除特定路徑
            if any(path in src_lower for path in ['/userapp/', '/app/', '/icon/', '/logo/', '/buy', '/shop', '/購物', '/shopping']):
                continue
            # 排除特定關鍵字
            if any(keyword in src_lower for keyword in ['buy-ic', 'shop', 'cart', '購物', 'shopping', 'app-icon', 'userapp']):
                continue
            
            alt = self._get_image_alt_text(img)
            # 排除 alt 文字中包含特定關鍵字
            if alt:
                alt_lower = alt.lower()
                if any(keyword in alt_lower for keyword in ['快點購', '購物', 'shop', 'buy', '購買']):
                    continue
            
            score = self._calculate_improved_relevance_score(img, src, alt)
            if score > best_score:
                best_score = score
                best_image = {'image_url': src, 'alt_text': self._clean_alt_text(alt)}
        return best_image

    def _get_image_alt_text(self, img):
        """獲取圖片的替代文字"""
        alt_text = img.get('alt', '').strip()
        if alt_text: return alt_text
        
        parent = img.parent
        if parent and parent.name == 'figure':
            figcaption = parent.find('figcaption')
            if figcaption and figcaption.get_text().strip(): return figcaption.get_text().strip()
            
            next_p = parent.find_next_sibling('p')
            if next_p:
                style = next_p.get('style', '')
                p_text = next_p.get_text().strip()
                if ('text-align:center' in style or 'text-align: center' in style) and p_text: return p_text
                if p_text and any(keyword in p_text for keyword in ['圖', '攝', '取自', '翻攝', '資料照']): return p_text
        
        if parent:
            next_sibling = img.find_next_sibling('figcaption')
            if next_sibling and next_sibling.get_text().strip(): return next_sibling.get_text().strip()
            
            prev_sibling = img.find_previous_sibling('figcaption')
            if prev_sibling and prev_sibling.get_text().strip(): return prev_sibling.get_text().strip()
            
            parent_next = parent.find_next_sibling('figcaption')
            if parent_next and parent_next.get_text().strip(): return parent_next.get_text().strip()
            
        return ''

    @staticmethod
    def _get_image_src(img):
        """獲取圖片來源 URL"""
        return (img.get('src') or 
                img.get('data-src') or 
                img.get('data-lazy') or 
                img.get('data-original') or 
                img.get('data-srcset', '').split(',')[0].strip().split(' ')[0])

    @staticmethod
    def _is_content_image(src, alt):
        """判斷是否為內容圖片"""
        # 排除 SVG 格式的圖片（通常是圖標或裝飾，不是主圖）
        if src.startswith('data:image/svg+xml') or src.lower().endswith('.svg'):
            return False
        
        src_lower, alt_lower = src.lower(), alt.lower()
        
        # 排除特定路徑的圖片（應用程式圖標、購物相關等）
        exclude_paths = ['/userapp/', '/app/', '/icon/', '/logo/', '/buy', '/shop', '/購物', '/shopping']
        if any(path in src_lower for path in exclude_paths):
            return False
        
        # 排除 URL 中包含特定關鍵字的圖片
        exclude_url_keywords = ['buy-ic', 'shop', 'cart', '購物', 'shopping', 'app-icon', 'userapp', '快點購']
        if any(keyword in src_lower for keyword in exclude_url_keywords):
            return False
        
        # 排除 alt 文字中包含特定關鍵字的圖片（可能是 logo、廣告、購物等）
        if alt:
            alt_lower = alt.lower()
            exclude_alt_keywords = ['logo', 'icon', 'avatar', 'banner', 'ad', '廣告', '贊助', '快點購', '購物', 'shop', 'buy', '購買']
            if any(keyword in alt_lower for keyword in exclude_alt_keywords):
                return False
        
        # 檢查是否為內容圖片的正面指標
        content_indicators = [
            '資料照', '圖片來源', '截自', '翻攝', '中天新聞', '記者', '攝影', 
            '圖／', '圖 /', '圖:', '圖：',  # 添加圖／相關關鍵字
            '.jpg', '.png', '.jpeg', '.webp'
        ]
        if any(indicator in alt or indicator.lower() in src_lower for indicator in content_indicators):
            return True
        
        # 如果 alt 文字長度合理且包含中文，可能是內容圖片
        if alt and 10 <= len(alt) <= 200:
            # 檢查是否包含中文（排除純英文的 logo/icon 描述）
            if re.search(r'[\u4e00-\u9fff]', alt):
                return True
        
        # 對於 storage.ctinews.com 的圖片，如果不在排除路徑中，認為是內容圖片
        if 'storage.ctinews.com' in src:
            if not any(path in src_lower for path in ['/userapp/', '/app/', '/icon/', '/logo/']):
                return True
        
        # 對於其他域名的圖片，如果 URL 包含常見的圖片格式，且不在排除列表中，也認為可能是內容圖片
        # 但需要更嚴格的檢查：必須有合理的 alt 文字或明顯的圖片格式
        if src_lower.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            # 如果有 alt 文字且包含中文，或 alt 文字長度合理
            if alt and (re.search(r'[\u4e00-\u9fff]', alt) or len(alt) >= 10):
                return True
            # 如果沒有 alt 文字，但 URL 看起來像是內容圖片（不包含排除關鍵字）
            if not alt:
                # 檢查 URL 是否包含明顯的非內容圖片特徵
                exclude_in_url = ['logo', 'icon', 'avatar', 'thumb', 'small', 'mini', 'button']
                if not any(keyword in src_lower for keyword in exclude_in_url):
                    return True
        
        return False

    def _calculate_main_image_score(self, img, src, alt):
        """計算主圖相關性分數"""
        score = 0
        all_images = self.soup.find_all('img')
        try:
            position = list(all_images).index(img)
            if position <= 5: score += [50, 30, 20, 10, 10, 10][position]
            else: score -= position * 2
        except ValueError: pass
        
        if alt:
            if '資料照' in alt or '中天新聞' in alt: score += 40
            if re.search(r'[\u4e00-\u9fff]{2,4}', alt): score += 20
            if 15 <= len(alt) <= 100: score += 15
            elif len(alt) > 100: score += 5
            if len(alt) > 50 and any(k in alt for k in ['圖', '攝', '翻攝', '資料照']): score += 25
        
        if 'storage.ctinews.com' in src:
            score += 30
            if '/compression/files/' in src: score += 20
            if 'cut-' in src: score += 15
        
        loading = img.get('loading', '')
        if loading == 'eager': score += 25
        elif loading == 'lazy': score += 10
        
        width, height = img.get('width'), img.get('height')
        if width and height:
            try:
                w, h = int(width), int(height)
                if w > h and w >= 300: score += 25
                elif w >= 200 and h >= 200: score += 15
            except ValueError: pass
        
        if any(k.lower() in src.lower() or k.lower() in alt.lower() for k in ['logo', 'icon', 'avatar', 'ad', 'banner', 'thumb']):
            score -= 30
        
        return score

    def _calculate_improved_relevance_score(self, img, src, alt):
        """改進版的相關性評分"""
        score = 10
        all_images = self.soup.find_all('img')
        try:
            position = list(all_images).index(img)
            score += max(0, 40 - position * 5)
        except ValueError: pass
        
        if alt:
            if '資料照／中天新聞' in alt: score += 60
            elif '資料照' in alt: score += 40
            elif '中天新聞' in alt: score += 30
            if any(k in alt for k in ['圖片來源', '截自', '翻攝', '記者', '圖／']): score += 20
            if re.search(r'[\u4e00-\u9fff]{2,}', alt): score += 15
            if len(alt) > 50: score += 10
        
        if 'storage.ctinews.com' in src:
            score += 35
            if '/compression/files/' in src: score += 15
        
        if src.lower().endswith(('.jpg', '.jpeg', '.png')): score += 10
        elif src.lower().endswith('.webp'): score += 5
        
        loading = img.get('loading', '')
        if loading == 'eager': score += 20
        elif loading == 'lazy': score += 10
        
        if any(p.lower() in src.lower() or p.lower() in alt.lower() for p in ['logo', 'icon', 'avatar', 'ad', 'banner', 'thumb', 'small']):
            score -= 40
        
        return score

    @staticmethod
    def _clean_alt_text(alt_text):
        """清理替代文字"""
        if not alt_text or not alt_text.strip(): return '無替代文字'
        
        result = Scraper._extract_text_in_parentheses(alt_text)
        if '翻攝畫面' in result: return '資料來源:中天新聞網'
        return result

    @staticmethod
    def _extract_text_in_parentheses(text):
        """提取括號內的文字"""
        if not text or text == '無替代文字': return text
        
        patterns = [r'（([^）]+)）', r'\(([^)]+)\)', r'【([^】]+)】', r'\[([^\]]+)\]']
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches: return max(matches, key=len)
        
        return text[:100] + "..." if len(text) > 100 else text

    @staticmethod
    def download_image(url):
        """下載圖片並返回 PIL Image 物件"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            }
            response = requests.get(url, headers=headers, verify=False, timeout=10)
            response.raise_for_status()
            return Image.open(io.BytesIO(response.content))
        except Exception:
            return None