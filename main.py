from typing import List, Dict
import feedparser
import requests
from bs4 import BeautifulSoup
import time
import random
import re
from datetime import datetime
import hashlib
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import google.generativeai as genai

# Configure Google Gemini API
GOOGLE_API_KEY = "AIzaSyA_Wkb7YQgw4vY7ECIW5NhoxIiaKb9WvcY"
genai.configure(api_key=GOOGLE_API_KEY)


class ArticleProcessor:
    def __init__(self):
        self.feed_url = "https://techcrunch.com/feed/"
        self.model = genai.GenerativeModel('gemini-pro')
        self.api_url = "http://127.0.0.1:8001/api/upload"

        # Web Scraping Setup
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        ]
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def fetch_articles(self) -> List[Dict]:
        print("\nParsing RSS feed...")
        feed = feedparser.parse(self.feed_url)
        print(f"Found {len(feed.entries)} entries in feed")
        articles = []

        for entry in feed.entries:
            article = {
                'title': entry.title,
                'link': entry.link,
                'published_date': entry.get('published', ''),
                'description': entry.get('description', ''),
                'author': entry.get('author', '')
            }
            articles.append(article)
            print(f"Parsed article: {article['title']}")
        return articles

    def scrape_article(self, url: str) -> str:
        try:
            time.sleep(random.uniform(1, 3))
            response = self.session.get(
                url,
                headers={'User-Agent': random.choice(self.user_agents)},
                timeout=15
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            print(f"\nScraping: {url}")

            # Get content
            article_content = soup.select_one('div.wp-block-post-content')
            if article_content:
                # Remove ads and unwanted elements
                for unwanted in article_content.select(
                        '.ad-unit, .wp-block-tc-ads-ad-slot, .marfeel-experience-inline-cta'):
                    unwanted.decompose()

                # Get paragraphs with wp-block-paragraph class
                paragraphs = article_content.select('p.wp-block-paragraph')

                if paragraphs:
                    # Filter out short paragraphs and clean text
                    valid_paragraphs = []
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if len(text) > 50 and not text.startswith('Image Credits:'):
                            valid_paragraphs.append(text)

                    if valid_paragraphs:
                        content = ' '.join(valid_paragraphs)
                        print(f"Found article content: {len(content)} chars")
                        return content

            print("No valid content found")
            return ""

        except Exception as e:
            print(f"Error scraping article: {str(e)}")
            return ""

    def rewrite_article(self, article: Dict) -> Dict:
        try:
            prompt = f"""
            Rewrite this technology article with proper HTML structure and SEO optimization. Follow this exact format:

            <article class="tech-analysis">
                <div class="article-header">
                    <h1>Main Title - Keep Original</h1>
                    <div class="article-meta">
                        <span class="publish-date">[Date]</span>
                        <span class="read-time">5 min read</span>
                    </div>
                </div>

                <div class="executive-summary">
                    <h2>Key Takeaways</h2>
                    <ul class="key-points">
                        [3-4 bullet points summarizing main points]
                    </ul>
                </div>

                <div class="main-content">
                    <section class="technology-overview">
                        <h2>Technology Overview</h2>
                        [Detailed explanation of the technology/announcement]
                    </section>

                    <section class="impact-analysis">
                        <h2>Industry Impact</h2>
                        [Analysis of how this affects the industry]
                    </section>

                    <section class="technical-details">
                        <h2>Technical Details</h2>
                        [Technical specifications or implementation details]
                    </section>

                    <section class="expert-insights">
                        <h2>Expert Analysis</h2>
                        <blockquote class="expert-quote">
                            [Include relevant expert quotes]
                        </blockquote>
                    </section>

                    <section class="user-implications">
                        <h2>What This Means for Users</h2>
                        <ul class="user-impact-points">
                            [Bullet points about user impact]
                        </ul>
                    </section>

                    <section class="future-outlook">
                        <h2>Future Implications</h2>
                        [Discussion of future developments and potential impacts]
                    </section>
                </div>

                <div class="conclusion">
                    <h2>Bottom Line</h2>
                    [Concise conclusion with key takeaway]
                </div>
            </article>

            Original Article Text:
            {article['content']}

            Requirements:
            1. Maintain journalistic professionalism
            2. Use proper HTML semantic structure
            3. Include relevant technical terms naturally
            4. Break down complex concepts clearly
            5. Add descriptive subheadings
            6. Use bullet points for better readability
            7. Include expert quotes when available
            8. Optimize for tech-focused SEO
            9. Keep technical accuracy
            10. Make content scannable and well-structured

            SEO Requirements:
            - Use relevant tech keywords naturally
            - Include semantic HTML5 tags
            - Proper heading hierarchy (h1, h2, h3)
            - Short, descriptive paragraphs
            - Include technical specifications where relevant
            - Link to related concepts (use <a> tags)
            - Add alt text for any images
            - Include meta description worthy content

            Please rewrite the article following this structure while maintaining technical accuracy and SEO optimization.
            """

            response = self.model.generate_content(prompt)

            if response.text:
                rewritten_content = response.text.strip()
                # Clean up any markdown or code block indicators
                rewritten_content = re.sub(r'^(?:html|```html|```)\s*', '', rewritten_content, flags=re.IGNORECASE)
                rewritten_content = re.sub(r'```\s*$', '', rewritten_content)

                # Ensure proper HTML structure
                if not rewritten_content.startswith('<article'):
                    rewritten_content = f'<article class="tech-analysis">{rewritten_content}</article>'

                return {
                    'title': article['title'],
                    'author': article.get('author', 'Tech Journalist'),
                    'date': article.get('date', datetime.now().strftime("%Y-%m-%d")),
                    'content': rewritten_content,
                    'preview': self.strip_html(rewritten_content)[:250] + '...',
                    'link': article.get('link', ''),
                    'category': 'technology'
                }
            else:
                print(f"Error: Empty response from Gemini for article: {article['title']}")
                return article

        except Exception as e:
            print(f"Error rewriting article: {str(e)}")
            return article

    def strip_html(self, text: str) -> str:
        return re.sub(r'<[^>]+>', '', text)

    def hash_md5(self, data):
        unique_data = f"{data['title']}-{data['link']}"
        return hashlib.md5(unique_data.encode()).hexdigest()

    def load_hashes(self):
        try:
            with open("hash-logs.txt", 'r') as f:
                return set(f.read().splitlines())
        except FileNotFoundError:
            return set()

    def save_hash(self, hash_str):
        with open("hash-logs.txt", 'a') as f:
            f.write(str(hash_str) + '\n')

    def does_hash_exist(self, hash_str, existing_hashes):
        return hash_str in existing_hashes

    def upload_article(self, article: Dict) -> bool:
        try:
            article_data = {
                'title': article['title'],
                'content': article['content'],
                'author': article.get('author', 'No author'),
                'preview': article.get('preview', ''),
                'date': article.get('date') or article.get('published_date', 'No date'),
                'link': article.get('link', ''),
                'category': 'technology'
            }

            try:
                response = requests.post(
                    self.api_url,
                    json=article_data,
                    timeout=10,
                    headers={'Content-Type': 'application/json'}
                )

                if response.status_code == 200:
                    print(f"Successfully uploaded article: {article['title']}")
                    return True
                else:
                    print(f"Failed to upload article. Status code: {response.status_code}")
                    print(f"Response: {response.text}")
                    return False

            except requests.exceptions.ConnectionError:
                print("Error: Could not connect to the API server. Make sure it's running.")
                return False
            except requests.exceptions.Timeout:
                print("Error: Request timed out")
                return False

        except Exception as e:
            print(f"Error uploading article: {str(e)}")
            return False

    def check_server(self):
        try:
            response = requests.get("http://127.0.0.1:8001/health")
            if response.status_code == 200:
                return True
            return False
        except requests.exceptions.ConnectionError:
            return False

    def process_articles(self):
        # Check if server is running first
        if not self.check_server():
            print("Error: FastAPI server is not running. Please start the server first using 'python run.py'")
            return []

        existing_hashes = self.load_hashes()
        processed_articles = []

        entries = self.fetch_articles()

        for entry in entries[:20]:  # Process first 20 articles
            try:
                article_hash = self.hash_md5(entry)

                if self.does_hash_exist(article_hash, existing_hashes):
                    print(f"Skipping duplicate article: {entry['title']}")
                    continue

                print(f"\nProcessing article: {entry['title']}")

                content = self.scrape_article(entry['link'])

                if content:
                    article = {
                        'title': entry['title'],
                        'content': content,
                        'author': entry.get('author', 'Unknown'),
                        'date': datetime.now().strftime("%Y-%m-%d"),
                        'link': entry['link'],
                        'preview': content[:250] + '...' if len(content) > 250 else content
                    }

                    if self.upload_article(article):
                        processed_articles.append(article)
                        self.save_hash(article_hash)
                        existing_hashes.add(article_hash)
                else:
                    print("No content found for article")

            except KeyboardInterrupt:
                print("\nProcessing interrupted by user")
                break
            except Exception as e:
                print(f"Error processing article: {str(e)}")
                continue

        print(f"\nProcessed {len(processed_articles)} articles.")
        return processed_articles


class FinanceArticleProcessor:
    def __init__(self):
        self.feed_urls = [
            "https://finance.yahoo.com/news/rssindex",
            "https://finance.yahoo.com/rss/headline?s=^GSPC",
            "https://finance.yahoo.com/rss/headline?s=^DJI",
            "https://finance.yahoo.com/rss/industry"
        ]
        self.model = genai.GenerativeModel('gemini-pro')
        self.api_url = "http://127.0.0.1:8001/api/upload"

        # Web Scraping Setup
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        ]
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def fetch_articles(self) -> List[Dict]:
        print("\nParsing Yahoo Finance RSS feeds...")
        articles = []

        for feed_url in self.feed_urls:
            try:
                feed = feedparser.parse(feed_url)
                print(f"Found {len(feed.entries)} entries in {feed_url}")

                for entry in feed.entries:
                    article = {
                        'title': entry.title,
                        'link': entry.link,
                        'published_date': entry.get('published', ''),
                        'description': entry.get('description', ''),
                        'author': entry.get('author', 'Yahoo Finance')
                    }
                    articles.append(article)
                    print(f"Parsed article: {article['title']}")

                time.sleep(1)  # Respect rate limiting

            except Exception as e:
                print(f"Error parsing feed {feed_url}: {str(e)}")
                continue

        return articles

    def scrape_article(self, url: str) -> str:
        try:
            time.sleep(random.uniform(2, 4))  # Respectful delay

            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://finance.yahoo.com',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Cache-Control': 'max-age=0',
            }

            response = self.session.get(url, headers=headers, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            print(f"\nScraping: {url}")

            # Updated content selectors for Yahoo Finance
            content_selectors = [
                'div[data-test-locator="articleBody"]',
                'div.caas-body',
                'div[data-test-id="article-body"]',
                'article',
                'div.content'
            ]

            article_content = None
            for selector in content_selectors:
                article_content = soup.select_one(selector)
                if article_content:
                    break

            if article_content:
                # Remove unwanted elements
                unwanted_classes = [
                    'ad-container', 'related-content', 'social-share',
                    'canvas-ad-label', 'comments-wrapper', 'modal',
                    'author-info', 'read-more', 'premium-promo'
                ]

                for unwanted_class in unwanted_classes:
                    for element in article_content.find_all(class_=lambda x: x and unwanted_class in x.lower()):
                        element.decompose()

                # Get paragraphs
                paragraphs = article_content.find_all(['p', 'h2', 'h3', 'ul', 'ol'])

                if paragraphs:
                    # Process and clean content
                    content_parts = []
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if len(text) > 20 and not any(
                                skip in text.lower() for skip in ['advertisement', 'sponsored', 'subscribe']):
                            content_parts.append(text)

                    if content_parts:
                        content = ' '.join(content_parts)
                        print(f"Found article content: {len(content)} chars")
                        return content

            print("No valid content found")
            return ""

        except Exception as e:
            print(f"Error scraping article: {str(e)}")
            return ""

    def rewrite_article(self, article: Dict) -> Dict:
        try:
            prompt = f"""
            Rewrite this financial article into a well-structured narrative without using symbols like percentages or trends. Focus on clarity and readability.

            Original Article:
            {article['content']}
            """

            response = self.model.generate_content(prompt)

            if response.text:
                rewritten_content = response.text.strip()
                # Ensure proper HTML structure
                if not rewritten_content.startswith('<article'):
                    rewritten_content = f'<article class="financial-analysis">{rewritten_content}</article>'

                return {
                    'title': article['title'],
                    'author': article.get('author', 'Finance Expert'),
                    'date': article.get('date', datetime.now().strftime("%Y-%m-%d")),
                    'content': rewritten_content,
                    'preview': self.strip_html(rewritten_content)[:250] + '...',
                    'link': article.get('link', ''),
                    'category': 'finance'
                }
            else:
                print(f"Error: Empty response from Gemini for article: {article['title']}")
                return article

        except Exception as e:
            print(f"Error rewriting article: {str(e)}")
            return article

    def strip_html(self, text: str) -> str:
        return re.sub(r'<[^>]+>', '', text)

    def hash_md5(self, article: Dict) -> str:
        content = f"{article['title']}{article['link']}"
        return hashlib.md5(content.encode()).hexdigest()

    def does_hash_exist(self, article_hash: str, existing_hashes: set) -> bool:
        return article_hash in existing_hashes

    def save_hash(self, article_hash: str):
        with open('processed_hashes.txt', 'a') as f:
            f.write(article_hash + '\n')

    def load_hashes(self) -> set:
        try:
            with open('processed_hashes.txt', 'r') as f:
                return set(line.strip() for line in f)
        except FileNotFoundError:
            return set()

    def upload_article(self, article: Dict) -> bool:
        try:
            response = requests.post(self.api_url, json=article)
            response.raise_for_status()
            print(f"Successfully uploaded article: {article['title']}")
            return True
        except Exception as e:
            print(f"Error uploading article: {str(e)}")
            return False

    def process_articles(self):
        print("Starting Yahoo Finance article processing...")
        existing_hashes = self.load_hashes()
        processed_articles = []

        entries = self.fetch_articles()

        for entry in entries[:20]:  # Process first 20 articles
            try:
                article_hash = self.hash_md5(entry)

                if self.does_hash_exist(article_hash, existing_hashes):
                    print(f"Skipping duplicate article: {entry['title']}")
                    continue

                print(f"\nProcessing article: {entry['title']}")

                content = self.scrape_article(entry['link'])

                if content:
                    article = {
                        'title': entry['title'],
                        'content': content,
                        'author': entry.get('author', 'Yahoo Finance'),
                        'date': datetime.now().strftime("%Y-%m-%d"),
                        'link': entry['link'],
                        'preview': content[:250] + '...' if len(content) > 250 else content
                    }

                    rewritten_article = self.rewrite_article(article)
                    if self.upload_article(rewritten_article):
                        processed_articles.append(rewritten_article)
                        self.save_hash(article_hash)
                        existing_hashes.add(article_hash)
                else:
                    print("No content found for article")

            except KeyboardInterrupt:
                print("\nProcessing interrupted by user")
                break
            except Exception as e:
                print(f"Error processing article: {str(e)}")
                continue

        print(f"\nProcessed {len(processed_articles)} Yahoo Finance articles.")
        return processed_articles


def main():
    try:
        print("\n=== Starting Technology Articles Processing ===")
        tech_processor = ArticleProcessor()
        tech_articles = tech_processor.process_articles()
        print(f"\nProcessed {len(tech_articles)} technology articles.")

        print("\n=== Starting Finance Articles Processing ===")
        finance_processor = FinanceArticleProcessor()
        finance_articles = finance_processor.process_articles()
        print(f"\nProcessed {len(finance_articles)} finance articles.")

        total_articles = len(tech_articles) + len(finance_articles)
        print(f"\n=== Total Articles Processed: {total_articles} ===")
        print("Technology Articles:", len(tech_articles))
        print("Finance Articles:", len(finance_articles))

    except Exception as e:
        print(f"Error in main processing: {str(e)}")
    finally:
        print("\n=== Processing Complete ===")


if __name__ == "__main__":
    main()