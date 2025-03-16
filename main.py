from typing import List, Dict, ClassVar, Callable, Optional
import feedparser
import requests
from bs4 import BeautifulSoup
import time
import random
import re
from datetime import datetime
import hashlib
import google.generativeai as genai
from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
import os

# Configure Google Gemini API
GOOGLE_API_KEY = "AIzaSyAquBLijcHEB5BycLmtf1Zg_NENmK1wrnA"
genai.configure(api_key=GOOGLE_API_KEY)

# Set OpenAI API key to a dummy value to avoid errors
os.environ["OPENAI_API_KEY"] = "dummy-key-not-used"

# --- Custom tool decorator that removes unwanted injected attributes ---
def my_tool(func: Callable) -> Callable:
    # First, decorate the function with the original tool decorator
    decorated = tool(func)
    # Remove any injected attribute named 'validate_tools' that causes schema errors.
    if hasattr(decorated, "validate_tools"):
        try:
            delattr(decorated, "validate_tools")
        except Exception:
            pass
    return decorated

class ArticleProcessor:
    def __init__(self):
        self.feed_url = "https://techcrunch.com/feed/"
        # Update to use Gemini 2.0 Flash-Lite model
        self.model = genai.GenerativeModel('gemini-2.0-flash-lite')  # Changed to gemini-2.0-flash-lite
        self.api_url = "http://127.0.0.1:8001/api/upload"
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        ]
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        from requests.adapters import HTTPAdapter
        from requests.packages.urllib3.util.retry import Retry
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
            article_content = soup.select_one('div.wp-block-post-content')
            if article_content:
                for unwanted in article_content.select('.ad-unit, .wp-block-tc-ads-ad-slot, .marfeel-experience-inline-cta'):
                    unwanted.decompose()
                paragraphs = article_content.select('p.wp-block-paragraph')
                if paragraphs:
                    valid_paragraphs = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50]
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
            # Validate input
            if not article.get('content'):
                print("Warning: Empty article content")
                return article

            # Extract content
            content = article.get('content', '')
            title = article.get('title', '')
            
            # Create a more detailed prompt for the LLM with styling instructions
            prompt = f"""
Please rewrite this technology article in your own words to avoid copyright issues.
Keep the same key information but change the wording completely.

Title: {title}

Original content:
{content[:3000]}

Format your response with proper HTML formatting and styling:
1. Start with a brief summary (2-3 sentences) in <p> tags with <strong> for important terms
2. Use <h2 style="font-size: 24px; margin-top: 20px; margin-bottom: 10px; color: #333;"> for section headings
3. For "What You Need to Know" section, use <ul> with <li> items that include <strong> for key points
4. For "The Details" section, use multiple <p> tags with <em> for emphasis on important concepts
5. For "Why It Matters" section, use <p> tags with at least one <strong> highlight
6. For "Bottom Line" section, use <p> with <strong> for the key takeaway
7. Include proper spacing between sections (margin-bottom on headings and paragraphs)

DO NOT include any text like "Here's a rewritten version" or mention avoiding copyright.
"""

            try:
                # Create a new model instance with the Flash-Lite model
                model = genai.GenerativeModel(
                    model_name="gemini-2.0-flash-lite",
                    generation_config={
                        'temperature': 0.4,
                        'top_p': 0.8,
                        'top_k': 40,
                        'max_output_tokens': 1024,
                    }
                )
                
                # Generate content with the new model
                response = model.generate_content(prompt)
                
                if response and hasattr(response, 'text') and response.text:
                    # Process the response
                    rewritten_content = response.text.strip()
                    print(f"Successfully rewrote article with LLM: {title}")
                    
                    # Clean up any remaining text about rewriting or copyright
                    rewritten_content = re.sub(r"Here's a rewritten version[^\.]*\.", "", rewritten_content)
                    rewritten_content = re.sub(r"avoiding copyright issues[^\.]*\.", "", rewritten_content)
                    
                    # Ensure proper HTML formatting
                    if "<h2" not in rewritten_content:
                        # If the model didn't use HTML, add it with proper styling
                        paragraphs = rewritten_content.split("\n\n")
                        formatted_html = ""
                        
                        # Add CSS styling
                        formatted_html += """
<style>
    h2 {
        font-size: 24px;
        margin-top: 20px;
        margin-bottom: 10px;
        color: #333;
        font-weight: bold;
    }
    p {
        font-size: 16px;
        line-height: 1.6;
        margin-bottom: 15px;
        color: #444;
    }
    ul {
        margin-bottom: 20px;
    }
    li {
        margin-bottom: 8px;
        line-height: 1.5;
    }
    .source {
        font-size: 14px;
        color: #666;
        margin-top: 30px;
        border-top: 1px solid #eee;
        padding-top: 10px;
    }
    strong {
        font-weight: bold;
        color: #222;
    }
    em {
        font-style: italic;
    }
</style>
"""
                        
                        # Add intro paragraph with some bold text
                        if paragraphs and len(paragraphs) > 0:
                            intro = paragraphs[0]
                            # Make some words bold
                            words = intro.split()
                            if len(words) > 5:
                                important_indices = [i for i in range(len(words)) if len(words[i]) > 5 and i % 7 == 0]
                                for i in important_indices:
                                    if i < len(words):
                                        words[i] = f"<strong>{words[i]}</strong>"
                            intro = " ".join(words)
                            formatted_html += f"<p>{intro}</p>\n\n"
                        
                        # Add What You Need to Know section
                        formatted_html += "<h2>What You Need to Know</h2>\n<ul>\n"
                        bullet_points = []
                        for para in paragraphs[1:]:
                            if para.startswith("•") or para.startswith("*"):
                                bullet_points.append(para.lstrip("•* "))
                        
                        # If no bullet points found, create some
                        if not bullet_points and len(paragraphs) > 1:
                            sentences = re.split(r'(?<=[.!?])\s+', " ".join(paragraphs[1:]))
                            bullet_points = sentences[:3] if len(sentences) >= 3 else sentences
                        
                        # Add bullet points with some bold text
                        for point in bullet_points[:3]:
                            # Make the first few words bold
                            words = point.split()
                            if len(words) > 3:
                                words[0] = f"<strong>{words[0]}</strong>"
                                if len(words) > 5 and len(words[2]) > 4:
                                    words[2] = f"<strong>{words[2]}</strong>"
                            point = " ".join(words)
                            formatted_html += f"<li>{point}</li>\n"
                        formatted_html += "</ul>\n\n"
                        
                        # Add The Details section with italics for emphasis
                        formatted_html += "<h2>The Details</h2>\n"
                        if len(paragraphs) > 2:
                            details = paragraphs[2]
                            # Add some italic text
                            words = details.split()
                            if len(words) > 8:
                                for i in range(len(words)):
                                    if len(words[i]) > 6 and i % 9 == 0:
                                        words[i] = f"<em>{words[i]}</em>"
                            details = " ".join(words)
                            formatted_html += f"<p>{details}</p>\n"
                            
                            if len(paragraphs) > 3:
                                more_details = paragraphs[3]
                                # Add some italic text
                                words = more_details.split()
                                if len(words) > 8:
                                    for i in range(len(words)):
                                        if len(words[i]) > 6 and i % 8 == 0:
                                            words[i] = f"<em>{words[i]}</em>"
                                more_details = " ".join(words)
                                formatted_html += f"<p>{more_details}</p>\n\n"
                        else:
                            formatted_html += "<p>This technology news covers recent developments and announcements in the industry. The article provides insights into the latest <em>trends</em> and <em>innovations</em> that are shaping the future of technology.</p>\n\n"
                        
                        # Add Why It Matters section with bold highlights
                        formatted_html += "<h2>Why It Matters</h2>\n"
                        if len(paragraphs) > 4:
                            why_matters = paragraphs[4]
                            # Add some bold text
                            words = why_matters.split()
                            if len(words) > 5:
                                important_indices = [i for i in range(len(words)) if len(words[i]) > 5 and i % 6 == 0]
                                for i in important_indices:
                                    if i < len(words):
                                        words[i] = f"<strong>{words[i]}</strong>"
                            why_matters = " ".join(words)
                            formatted_html += f"<p>{why_matters}</p>\n\n"
                        else:
                            formatted_html += "<p>This development is <strong>significant</strong> for the technology industry and could <strong>impact</strong> how users interact with these technologies in the future.</p>\n\n"
                        
                        # Add Bottom Line section with bold conclusion
                        formatted_html += "<h2>Bottom Line</h2>\n"
                        if len(paragraphs) > 5:
                            bottom_line = paragraphs[5]
                            formatted_html += f"<p><strong>{bottom_line}</strong></p>\n"
                        else:
                            first_sentence = paragraphs[0].split('.')[0] if paragraphs and len(paragraphs) > 0 else "This represents an important development in the technology industry"
                            formatted_html += f"<p><strong>{first_sentence}.</strong></p>\n"
                        
                        rewritten_content = formatted_html
                    else:
                        # If HTML is already present, ensure it has proper styling
                        # Add CSS styling at the beginning
                        css_styling = """
<style>
    h2 {
        font-size: 24px;
        margin-top: 20px;
        margin-bottom: 10px;
        color: #333;
        font-weight: bold;
    }
    p {
        font-size: 16px;
        line-height: 1.6;
        margin-bottom: 15px;
        color: #444;
    }
    ul {
        margin-bottom: 20px;
    }
    li {
        margin-bottom: 8px;
        line-height: 1.5;
    }
    .source {
        font-size: 14px;
        color: #666;
        margin-top: 30px;
        border-top: 1px solid #eee;
        padding-top: 10px;
    }
    strong {
        font-weight: bold;
        color: #222;
    }
    em {
        font-style: italic;
    }
</style>
"""
                        rewritten_content = css_styling + rewritten_content
                        
                        # Enhance existing HTML with better styling
                        # Add style attributes to h2 tags if they don't have them
                        rewritten_content = re.sub(
                            r'<h2(?!\s+style)>', 
                            '<h2 style="font-size: 24px; margin-top: 20px; margin-bottom: 10px; color: #333; font-weight: bold;">', 
                            rewritten_content
                        )
                    
                    # Add source attribution at the end with styling
                    formatted_content = f"{rewritten_content}\n\n<p class='source' style='font-size: 14px; color: #666; margin-top: 30px; border-top: 1px solid #eee; padding-top: 10px;'>Source: <a href='{article.get('link', '')}'>{article.get('link', '')}</a></p>"
                    
                    # Create a preview without mentioning rewriting or copyright
                    first_paragraph = re.search(r'<p>(.*?)</p>', rewritten_content)
                    preview = first_paragraph.group(1) if first_paragraph else rewritten_content[:250]
                    preview = re.sub(r"<[^>]+>", "", preview)  # Remove HTML tags from preview
                    preview = re.sub(r"Here's a rewritten version[^\.]*\.", "", preview)
                    preview = re.sub(r"avoiding copyright issues[^\.]*\.", "", preview)
                    
                    return {
                        'title': article['title'],
                        'author': article.get('author', 'Tech Journalist'),
                        'date': article.get('date', datetime.now().strftime("%Y-%m-%d")),
                        'content': formatted_content,
                        'preview': preview[:250] + '...' if len(preview) > 250 else preview,
                        'link': article.get('link', ''),
                        'category': 'technology'
                    }
                else:
                    print(f"Warning: Empty response from LLM for article: {title}")
                    return self._create_fallback_article_html(article)
                
            except Exception as e:
                print(f"Error using Gemini API: {str(e)}")
                return self._create_fallback_article_html(article)
                
        except Exception as e:
            print(f"Error in article rewriting: {str(e)}")
            return self._create_fallback_article_html(article)

    def _create_fallback_article_html(self, article: Dict) -> Dict:
        """Create a fallback article with proper HTML formatting when LLM fails"""
        content = article.get('content', '')
        title = article.get('title', '')
        
        # Extract sentences for better processing
        sentences = re.split(r'(?<=[.!?])\s+', content)
        
        # Create a simple summary
        summary = ' '.join(sentences[:3]) if len(sentences) >= 3 else content[:300]
        
        # Create a fallback article with proper HTML formatting and styling
        fallback_content = f"""
<style>
    h2 {{
        font-size: 24px;
        margin-top: 20px;
        margin-bottom: 10px;
        color: #333;
        font-weight: bold;
    }}
    p {{
        font-size: 16px;
        line-height: 1.6;
        margin-bottom: 15px;
        color: #444;
    }}
    ul {{
        margin-bottom: 20px;
    }}
    li {{
        margin-bottom: 8px;
        line-height: 1.5;
    }}
    .source {{
        font-size: 14px;
        color: #666;
        margin-top: 30px;
        border-top: 1px solid #eee;
        padding-top: 10px;
    }}
    strong {{
        font-weight: bold;
        color: #222;
    }}
    em {{
        font-style: italic;
    }}
</style>

<p>{summary}</p>

<h2 style="font-size: 24px; margin-top: 20px; margin-bottom: 10px; color: #333; font-weight: bold;">What You Need to Know</h2>
<ul>
    <li><strong>Technology Impact:</strong> This article discusses important developments in the technology industry.</li>
    <li><strong>Recent Developments:</strong> The information covers recent news and announcements in the tech sector.</li>
    <li><strong>User Implications:</strong> The technology described could have <em>significant implications</em> for users and businesses.</li>
</ul>

<h2 style="font-size: 24px; margin-top: 20px; margin-bottom: 10px; color: #333; font-weight: bold;">The Details</h2>
<p>This technology news covers recent developments and announcements in the industry. The article provides insights into the latest <em>trends</em> and <em>innovations</em> that are shaping the future of technology.</p>
<p>While we couldn't process all the specific details automatically, the article appears to discuss <strong>significant industry trends</strong> and updates that are relevant to both consumers and professionals in the field.</p>

<h2 style="font-size: 24px; margin-top: 20px; margin-bottom: 10px; color: #333; font-weight: bold;">Why It Matters</h2>
<p>Staying informed about <strong>technological advancements</strong> helps users and businesses make better decisions. This particular development may influence how people interact with technology in the future, potentially changing workflows, consumer experiences, or business operations.</p>

<h2 style="font-size: 24px; margin-top: 20px; margin-bottom: 10px; color: #333; font-weight: bold;">Bottom Line</h2>
<p><strong>This represents an important development in the technology industry that's worth following closely.</strong></p>

<p class='source' style='font-size: 14px; color: #666; margin-top: 30px; border-top: 1px solid #eee; padding-top: 10px;'>Source: <a href="{article.get('link', '')}">{article.get('link', '')}</a></p>
"""
        
        # Create a preview without mentioning rewriting
        preview = re.sub(r"<[^>]+>", "", summary)  # Remove HTML tags from preview
        
        return {
            'title': article['title'],
            'author': article.get('author', 'Tech Journalist'),
            'date': article.get('date', datetime.now().strftime("%Y-%m-%d")),
            'content': fallback_content,
            'preview': preview[:250] + '...' if len(preview) > 250 else preview,
            'link': article.get('link', ''),
            'category': 'technology'
        }

    def strip_html(self, text: str) -> str:
        return re.sub(r'<[^>]+>', '', text)

    def hash_md5(self, data: Dict) -> str:
        unique_data = f"{data.get('title', '')}-{data.get('link', '')}"
        return hashlib.md5(unique_data.encode()).hexdigest()

    def load_hashes(self):
        try:
            with open("hash-logs.txt", 'r') as f:
                return set(f.read().splitlines())
        except FileNotFoundError:
            return set()

    def save_hash(self, hash_str: str):
        with open("hash-logs.txt", 'a') as f:
            f.write(str(hash_str) + '\n')

    def does_hash_exist(self, hash_str: str, existing_hashes: set) -> bool:
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
        except Exception as e:
            print(f"Error uploading article: {str(e)}")
            return False

# Agent classes now use my_tool instead of tool
class ScraperAgent(Agent):
    def __init__(self, processor: ArticleProcessor):
        # Store processor in a local variable for closure access
        proc = processor
        
        # Define tools as local functions
        @my_tool
        def fetch_articles() -> List[Dict]:
            """Fetches articles from RSS feeds."""
            return proc.fetch_articles()
            
        @my_tool
        def scrape_article(url: str) -> str:
            """Scrapes full content of an article from its URL."""
            return proc.scrape_article(url)
            
        # Initialize the Agent with the tools
        super().__init__(
            role="Scraper", 
            goal="Scrape articles from RSS feeds",
            backstory="I am an expert web scraper specialized in extracting content from technology websites and RSS feeds.",
            tools=[fetch_articles, scrape_article],
            verbose=True
        )
        # Don't set processor as an attribute to avoid Pydantic validation issues

class RewriterAgent(Agent):
    def __init__(self, processor: ArticleProcessor):
        # Store processor in a local variable for closure access
        proc = processor
        
        # Define tools as local functions
        @my_tool
        def rewrite_article(article: Dict) -> Dict:
            """Rewrites an article using AI for better structure and SEO."""
            return proc.rewrite_article(article)
            
        # Initialize the Agent with the tools
        super().__init__(
            role="Rewriter", 
            goal="Rewrite articles using AI",
            backstory="I am an expert content writer with years of experience in SEO optimization and article restructuring.",
            tools=[rewrite_article],
            verbose=True
        )
        # Don't set processor as an attribute to avoid Pydantic validation issues

class PublisherAgent(Agent):
    def __init__(self, api_url: str):
        # Store api_url in a local variable for closure access
        url = api_url
        
        # Define tools as local functions
        @my_tool
        def publish_article(article: Dict) -> bool:
            """Publishes an article to the API endpoint."""
            try:
                response = requests.post(
                    url,
                    json={
                        'title': article['title'],
                        'content': article['content'],
                        'author': article.get('author', 'No author'),
                        'preview': article.get('preview', ''),
                        'date': article.get('date') or article.get('published_date', 'No date'),
                        'link': article.get('link', ''),
                        'category': 'technology'
                    },
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
            except Exception as e:
                print(f"Error uploading article: {str(e)}")
                return False
                
        # Initialize the Agent with the tools
        super().__init__(
            role="Publisher", 
            goal="Publish articles to API",
            backstory="I am a publishing specialist responsible for delivering content to various platforms and APIs.",
            tools=[publish_article],
            verbose=True
        )
        # Don't set api_url as an attribute to avoid Pydantic validation issues

def create_crew(processor: ArticleProcessor) -> Crew:
    # Import here to avoid circular imports
    from langchain_openai import ChatOpenAI
    
    # Use a dummy OpenAI model that won't actually be called
    # CrewAI requires an OpenAI-compatible LLM, but we'll bypass it
    dummy_llm = ChatOpenAI(
        model_name="gpt-3.5-turbo",  # This won't be used
        temperature=0.7
    )
    
    # Create agents without setting LLM
    scraper = ScraperAgent(processor)
    rewriter = RewriterAgent(processor)
    publisher = PublisherAgent("http://127.0.0.1:8001/api/upload")

    # Create tasks with simplified descriptions
    fetch_task = Task(
        description="Fetch recent technology articles from RSS feeds",
        expected_output="A list of articles with metadata",
        agent=scraper
    )
    
    scrape_task = Task(
        description="Scrape the full content of each article",
        expected_output="The complete text content of each article",
        agent=scraper
    )
    
    rewrite_task = Task(
        description="Rewrite each article to be more concise and structured",
        expected_output="Rewritten articles with improved structure",
        agent=rewriter
    )
    
    publish_task = Task(
        description="Publish the rewritten articles to the API",
        expected_output="Confirmation of successful publication",
        agent=publisher
    )

    # Create crew with minimal configuration
    crew_instance = Crew(
        agents=[scraper, rewriter, publisher],
        tasks=[fetch_task, scrape_task, rewrite_task, publish_task],
        verbose=True,  # Changed from 2 to True
        process=Process.sequential,
        llm=dummy_llm
    )
    
    return crew_instance

def process_articles_manually(processor: ArticleProcessor):
    """Process articles manually without using CrewAI"""
    try:
        print("Starting manual article processing...")
        
        # 1. Fetch articles
        print("\nFetching articles...")
        articles = processor.fetch_articles()
        if not articles:
            print("No articles found.")
            return
        
        print(f"Found {len(articles)} articles.")
        
        # 2. Process each article
        processed_articles = []
        for i, article in enumerate(articles[:3]):  # Process only first 3 articles
            print(f"\nProcessing article {i+1}/{min(3, len(articles))}: {article['title']}")
            
            # Scrape content
            content = processor.scrape_article(article['link'])
            if not content:
                print(f"Skipping article - no content found: {article['title']}")
                continue
                
            # Add content to article
            article['content'] = content
            
            # Rewrite article
            rewritten = processor.rewrite_article(article)
            if rewritten == article:
                print(f"Warning: Article rewriting failed: {article['title']}")
            
            # Upload article
            success = processor.upload_article(rewritten)
            if success:
                processed_articles.append(rewritten)
                print(f"Successfully processed: {rewritten['title']}")
            else:
                print(f"Failed to upload: {rewritten['title']}")
        
        return processed_articles
        
    except Exception as e:
        print(f"Error in manual processing: {str(e)}")
        return []

def main():
    try:
        print("\n=== Starting Technology Articles Processing ===")
        
        # Initialize processor
        processor = ArticleProcessor()
        
        # Skip CrewAI and go straight to manual processing
        print("Starting manual article processing...")
        result = process_articles_manually(processor)
        print(f"Manual processing complete. Processed {len(result)} articles.")
            
    except Exception as e:
        print(f"Critical error in main processing: {str(e)}")
    finally:
        print("\n=== Processing Complete ===")

if __name__ == "__main__":
    main()


