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
        """方法1：找到文章內容區域的第一張有意義圖片"""
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
        
        for img in content_area.find_all('img'):
            src = self._get_image_src(img)
            if not src: continue
            if not src.startswith(('http://', 'https://')):
                src = urljoin(self.base_url, src)
            
            alt = self._get_image_alt_text(img)
            if self._is_content_image(src, alt):
                return {'image_url': src, 'alt_text': self._clean_alt_text(alt)}
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
            
            alt = self._get_image_alt_text(img)
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
        exclude_patterns = [
            r'logo', r'icon', r'avatar', r'ad[^a-z]', r'banner', r'button', r'arrow', 
            r'bg[^a-z]', r'background', r'_80x80', r'thumb', r'small', r'mini',
            r'facebook', r'twitter', r'instagram', r'youtube', r'share', r'social'
        ]
        src_lower, alt_lower = src.lower(), alt.lower()
        if any(re.search(p, src_lower) or re.search(p, alt_lower) for p in exclude_patterns):
            return False
        
        content_indicators = ['資料照', '圖片來源', '截自', '翻攝', '中天新聞', '記者', '攝影', '.jpg', '.png', '.jpeg', '.webp']
        if any(indicator in alt or indicator.lower() in src_lower for indicator in content_indicators):
            return True
        
        if alt and 10 <= len(alt) <= 200: return True
        if 'storage.ctinews.com' in src: return True
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