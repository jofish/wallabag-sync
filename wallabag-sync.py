#!/usr/bin/env python3
"""
Wallabag Sync and HTML Exporter

This script checks a Wallabag account for new saves and exports them as HTML files.
Designed to be run from cron for periodic checking.
Requires: requests library (pip install requests)

Mainly created by Claude, with a few tweaks by me.

You'll need to put in your configuration, down starting around line 50 or so.
Regular usage (put this in your cron file): python wallabag-sync.py
Import from your Pocket save file: python wallabag-sync.py --import-csv bookmarks.csv (optional: add --dryrun for, well, a dry run)
Custom config file: python wallabag-sync.py --config /path/to/custom_config.json --import-csv bookmarks.csv

"""

import requests, json, time, os, csv, argparse, re, logging
from datetime import datetime, timezone
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('wallabag_sync.log'),
        logging.StreamHandler()
    ]
)

class Wallabagsync:
    def __init__(self, config_file='wallabag_config.json'):
        """Initialize the Wallabag sync with configuration."""
        self.config = self.load_config(config_file)
        self.access_token = None
        self.last_check_file = 'last_check.json'
        self.output_dir = Path(self.config.get('output_directory', 'wallabag_exports'))
        self.output_dir.mkdir(exist_ok=True)
        
    def load_config(self, config_file):
        """Load configuration from JSON file."""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            # Create example config file
            example_config = {
                "wallabag_url": "https://your-wallabag-instance.com",
                "client_id": "your_client_id",
                "client_secret": "your_client_secret", 
                "username": "your_username",
                "password": "your_password",
                "output_directory": "wallabag_exports",
                "check_interval": 300  #i think you can ignore this now.
            }
            with open(config_file, 'w') as f:
                json.dump(example_config, f, indent=2)
            
            print(f"Created example config file: {config_file}")
            print("Please edit it with your Wallabag credentials and settings.")
            exit(1)
    
    def get_access_token(self):
        """Get access token from Wallabag API."""
        token_url = f"{self.config['wallabag_url']}/oauth/v2/token"
        
        token_data = {
            'grant_type': 'password',
            'client_id': self.config['client_id'],
            'client_secret': self.config['client_secret'],
            'username': self.config['username'],
            'password': self.config['password']
        }
        
        try:
            response = requests.post(token_url, data=token_data)
            response.raise_for_status()
            
            token_info = response.json()
            self.access_token = token_info['access_token']
            logging.info("Successfully obtained access token")
            return True
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get access token: {e}")
            return False
    
    def get_last_check_time(self):
        """Get the timestamp of the last check."""
        try:
            with open(self.last_check_file, 'r') as f:
                data = json.load(f)
                return data.get('last_check_time')
        except FileNotFoundError:
            return None
    
    def save_last_check_time(self, timestamp):
        """Save the timestamp of the current check."""
        with open(self.last_check_file, 'w') as f:
            json.dump({'last_check_time': timestamp}, f)
    
    def get_entries(self, since_timestamp=None):
        """Get entries from Wallabag API."""
        if not self.access_token:
            if not self.get_access_token():
                return []
        
        entries_url = f"{self.config['wallabag_url']}/api/entries"
        headers = {'Authorization': f'Bearer {self.access_token}'}
        
        params = {
            'perPage': 100,   #it looks to me like it will only ever load one page of these? no need to fix right now.
            'order': 'desc',
            'sort': 'created'
        }
        
        # Add since parameter if we have a last check time
        if since_timestamp:
            params['since'] = int(since_timestamp)
        
        try:
            response = requests.get(entries_url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            entries = data.get('_embedded', {}).get('items', [])
            
            logging.info(f"Retrieved {len(entries)} entries from Wallabag")
            return entries
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get entries: {e}")
            return []
    
    def get_entry_content(self, entry_id):
        """Get the full content of a specific entry."""
        if not self.access_token:
            if not self.get_access_token():
                return None
        
        entry_url = f"{self.config['wallabag_url']}/api/entries/{entry_id}"
        headers = {'Authorization': f'Bearer {self.access_token}'}
        
        try:
            response = requests.get(entry_url, headers=headers)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get entry content for ID {entry_id}: {e}")
            return None
    
    def sanitize_filename(self, filename):
        """Sanitize filename for safe file system usage."""
        # Remove or replace problematic characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = filename.strip()
        
        # Limit length
        if len(filename) > 200:
            filename = filename[:200]
        
        return filename or "untitled"
    
    def create_html_export(self, entry):
        """Create HTML export of an entry."""
        title = entry.get('title', 'Untitled')
        url = entry.get('url', '')
        content = entry.get('content', '')
        created_at = entry.get('created_at', '')
        
        # Parse created_at timestamp
        try:
            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            formatted_date = created_dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            formatted_date = created_at
        
        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
            color: #333;
        }}
        .header {{
            border-bottom: 1px solid #eee;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .title {{
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        .meta {{
            color: #666;
            font-size: 0.9em;
        }}
        .url {{
            word-break: break-all;
            margin: 10px 0;
        }}
        .content {{
            margin-top: 30px;
        }}
        .content img {{
            max-width: 100%;
            height: auto;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title">{title}</div>
        <div class="meta">
            <div>Saved on: {formatted_date}</div>
            <div class="url">Original URL: <a href="{url}">{url}</a></div>
        </div>
    </div>
    <div class="content">
        {content}
    </div>
</body>
</html>"""
        
        return html_template
    
    def add_entry_to_wallabag(self, url, title=None, tags=None):
        """Add a new entry to Wallabag."""
        if not self.access_token:
            if not self.get_access_token():
                return False
        
        entries_url = f"{self.config['wallabag_url']}/api/entries"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        data = {'url': url}
        if title:
            data['title'] = title
        if tags:
            data['tags'] = tags
        
        try:
            response = requests.post(entries_url, headers=headers, json=data)
            response.raise_for_status()
            
            entry = response.json()
            logging.info(f"Added entry: {title or url}")
            return entry
            
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 409:
                    logging.info(f"Entry already exists: {title or url}")
                    return True  # Not an error, just already exists
                else:
                    logging.error(f"Failed to add entry {title or url}: {e.response.status_code} - {e.response.text}")
            else:
                logging.error(f"Failed to add entry {title or url}: {e}")
            return False
    
    def import_from_csv(self, csv_file, dry_run=False):
        """Import entries from a CSV file."""
        if not os.path.exists(csv_file):
            logging.error(f"CSV file not found: {csv_file}")
            return False
        
        logging.info(f"Starting CSV import from: {csv_file}")
        if dry_run:
            logging.info("DRY RUN MODE - no entries will be added")
        
        imported_count = 0
        error_count = 0
        skipped_count = 0
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                # Try to detect if there's a header by checking first line
                sample = f.read(1024)
                f.seek(0)
                
                # Check if first line looks like a header
                first_line = f.readline().strip()
                f.seek(0)
                
                has_header = ('title' in first_line.lower() or 'url' in first_line.lower())
                
                reader = csv.reader(f)
                
                if has_header:
                    next(reader)  # Skip header row
                
                for row_num, row in enumerate(reader, start=1):
                    if len(row) < 2:
                        logging.warning(f"Row {row_num}: Not enough columns, skipping")
                        skipped_count += 1
                        continue
                    
                    title = row[0].strip()
                    url = row[1].strip()
                    
                    if not url:
                        logging.warning(f"Row {row_num}: Empty URL, skipping")
                        skipped_count += 1
                        continue
                    
                    # Extract tags if available (assuming format: tag1,tag2,tag3)
                    tags = None
                    if len(row) > 4 and row[4].strip():
                        tags = row[4].strip()
                    
                    logging.info(f"Processing: {title} -> {url}")
                    
                    if not dry_run:
                        if self.add_entry_to_wallabag(url, title, tags):
                            imported_count += 1
                        else:
                            error_count += 1
                        
                        # Add small delay to be nice to the API
                        time.sleep(0.5)
                    else:
                        imported_count += 1
        
        except Exception as e:
            logging.error(f"Error reading CSV file: {e}")
            return False
        
        logging.info(f"CSV import completed:")
        logging.info(f"  Imported: {imported_count}")
        logging.info(f"  Errors: {error_count}")
        logging.info(f"  Skipped: {skipped_count}")
        
        return True
        """Export a single entry as HTML file."""
        entry_id = entry.get('id')
        title = entry.get('title', 'Untitled')
        
        # Get full content
        full_entry = self.get_entry_content(entry_id)
        if not full_entry:
            logging.error(f"Could not retrieve full content for entry {entry_id}")
            return False
        
        # Create HTML content
        html_content = self.create_html_export(full_entry)
        
        # Create filename
        created_at = entry.get('created_at', '')
        try:
            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            date_prefix = created_dt.strftime('%Y-%m-%d')
        except:
            date_prefix = 'unknown-date'
        
        filename = f"{date_prefix}_{self.sanitize_filename(title)}.html"
        filepath = self.output_dir / filename
        
        # Save HTML file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logging.info(f"Exported: {filename}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to save file {filename}: {e}")
            return False
    
    def check_for_new_entries(self):
        """Check for new entries and export them."""
        last_check = self.get_last_check_time()
        current_time = time.time()
        
        logging.info("Checking for new entries...")
        
        # Get entries since last check
        entries = self.get_entries(since_timestamp=last_check)
        
        if not entries:
            logging.info("No new entries found")
            self.save_last_check_time(current_time)
            return
        
        # Filter for truly new entries if we have a last check time
        new_entries = []
        if last_check:
            for entry in entries:
                try:
                    created_at = entry.get('created_at', '')
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    created_timestamp = created_dt.timestamp()
                    
                    if created_timestamp > last_check:
                        new_entries.append(entry)
                except:
                    # Include entry if we can't parse the date
                    new_entries.append(entry)
        else:
            # First run - consider all entries as new
            new_entries = entries
        
        logging.info(f"Found {len(new_entries)} new entries to export")
        
        # Export new entries
        exported_count = 0
        for entry in new_entries:
            if self.export_entry(entry):
                exported_count += 1
        
        logging.info(f"Successfully exported {exported_count} entries")
        
        # Update last check time
        self.save_last_check_time(current_time)
    
    def run_once(self):
        """Run a single check for new entries."""
        logging.info("Starting Wallabag check")
        logging.info(f"Output directory: {self.output_dir}")
        
        try:
            self.check_for_new_entries()
            logging.info("Wallabag check completed successfully")
        except Exception as e:
            logging.error(f"Error during Wallabag check: {e}")
            raise

def main():
    """Main function with command line argument support."""
    parser = argparse.ArgumentParser(description='Wallabag sync and CSV Importer')
    parser.add_argument('--import-csv', metavar='FILE', help='Import entries from CSV file')
    parser.add_argument('--dry-run', action='store_true', help='Preview CSV import without adding entries')
    parser.add_argument('--config', metavar='FILE', default='wallabag_config.json', help='Config file path')
    
    args = parser.parse_args()
    
    sync = Wallabagsync(args.config)
    
    if args.import_csv:
        # CSV import mode
        sync.import_from_csv(args.import_csv, dry_run=args.dry_run)
    else:
        # Normal syncing mode
        sync.run_once()

if __name__ == "__main__":
    main()
