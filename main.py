import feedparser
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import re
from typing import Dict, List
import os
from datetime import datetime
import random
import time
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import hashlib

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
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
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
                for unwanted in article_content.select('.ad-unit, .wp-block-tc-ads-ad-slot, .marfeel-experience-inline-cta'):
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
            prompt = (
                "You are a direct, no-BS tech expert who focuses on practical value and results. "
                "Add citations and references to help non-technical readers understand easily.\n\n"
                "Writing Style Rules:\n"
                "1) Use specific numbers/metrics\n"
                "2) Focus on actionable insights\n"
                "3) Include citations and expert references\n"
                "4) Add a P.S.\n"
                "5) Add links to the references if you think its good\n\n"
                "Content Guidelines:\n"
                "- Use conversational, simple language (7th grade level)\n"
                "- Write short, punchy sentences\n"
                "- Include analogies and examples\n"
                "- Use personal anecdotes where relevant\n"
                "- Add bullet points for key information\n"
                "- Split long sentences for readability\n"
                "- Use bold/italic for emphasis\n"
                "- Avoid jargon and promotional language\n\n"
                f"Please rewrite this tech article following the above guidelines:\n\n{article['content']}\n\n"
                "Format the article in clean HTML with appropriate tags for headings, paragraphs, and lists."
            )

            response = self.model.generate_content(prompt)
            
            if response.text:
                rewritten_content = response.text.strip()
                # Remove 'html' prefix if present
                rewritten_content = re.sub(r'^(?:html|```html|```)\s*', '', rewritten_content, flags=re.IGNORECASE)
                
                return {
                    'title': article['title'],
                    'author': article.get('author'),
                    'date': article.get('date'),
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

def main():
    processor = ArticleProcessor()
    processor.process_articles()

if __name__ == "__main__":
    main()