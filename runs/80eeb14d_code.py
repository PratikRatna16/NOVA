import requests
import os
import json
import argparse
import time
from functools import lru_cache

class GitHubClient:
    def __init__(self, api_key=None, enable_cache=True):
        self.api_key = api_key or os.environ.get('GITHUB_API_KEY', '')
        self.base_url = 'https://api.github.com'
        self.enable_cache = enable_cache
        self._cache = {}

    def _get_headers(self):
        headers = {}
        if self.api_key:
            headers['Authorization'] = f'token {self.api_key}'
        return headers

    def _make_request(self, url, params=None, max_retries=3):
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=self._get_headers(), params=params)
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                elif response.status_code == 404:
                    return {'error': 'Not found', 'status_code': 404}
                elif response.status_code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    return {'error': response.reason, 'status_code': response.status_code}
            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    return {'error': str(e), 'status_code': 0}
                time.sleep(2 ** attempt)
        return {'error': 'Max retries exceeded', 'status_code': 0}

    def get_user(self, username):
        if self.enable_cache and username in self._cache:
            return self._cache[username].get('user')
        url = f'{self.base_url}/users/{username}'
        result = self._make_request(url)
        if self.enable_cache and result and 'error' not in result:
            if username not in self._cache:
                self._cache[username] = {}
            self._cache[username]['user'] = result
        return result

    def get_repos(self, username, page=1, per_page=10):
        if self.enable_cache and username in self._cache:
            cache_key = f'repos_{page}_{per_page}'
            if cache_key in self._cache[username]:
                return self._cache[username][cache_key]
        url = f'{self.base_url}/users/{username}/repos'
        params = {'page': page, 'per_page': per_page}
        result = self._make_request(url, params)
        if self.enable_cache and result and 'error' not in result:
            if username not in self._cache:
                self._cache[username] = {}
            self._cache[username][f'repos_{page}_{per_page}'] = result
        return result

def main():
    parser = argparse.ArgumentParser(description='GitHub API Client')
    parser.add_argument('--api-key', help='GitHub API key')
    parser.add_argument('--cache', action='store_true', help='Enable caching')
    parser.add_argument('--page', type=int, default=1, help='Page number for repos')
    parser.add_argument('--per-page', type=int, default=10, help='Per page for repos')
    parser.add_argument('username', help='GitHub username')
    args = parser.parse_args()

    client = GitHubClient(api_key=args.api_key, enable_cache=args.cache)
    user_data = client.get_user(args.username)
    repo_data = client.get_repos(args.username, page=args.page, per_page=args.per_page)

    print(json.dumps(user_data, indent=4))
    print(json.dumps(repo_data, indent=4))

if __name__ == '__main__':
    main()