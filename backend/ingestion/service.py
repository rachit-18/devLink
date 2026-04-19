from github import Github
import os
from dotenv import load_dotenv
from github.GithubException import RateLimitExceededException
from typing import List, Dict, Any

load_dotenv()

class GitHubService:
    def __init__(self):
        token = os.getenv('GITHUB_TOKEN')
        if not token:
            raise ValueError("GITHUB_TOKEN is not set in environment variables.")
        self.gh = Github(token)

    def fetch_repo(self, repo_name: str, max_files: int = 5) -> List[Dict[str, Any]]:
        """
        Fetches a repository from GitHub using the provided repository name.
        """
        print(f"Fetching repository: {repo_name}")
        try:
            repo = self.gh.get_repo(repo_name)
            contents = repo.get_contents("")
            if not isinstance(contents, list):
                contents = [contents]
                
            repo_data = []
            processed_count = 0
            
            # Using a stack for iterative traversal to handle directories
            stack = list(contents)
            
            allowed_extensions = {'.py', '.js', '.java', '.cpp', '.c', '.rb', '.go', '.ts', '.php', '.tsx', '.jsx'}
            
            while stack and processed_count < max_files:
                file_content = stack.pop(0)
                
                if file_content.type == "dir":
                    try:
                        items = repo.get_contents(file_content.path)
                        if isinstance(items, list):
                            stack.extend(items)
                        else:
                            stack.append(items)
                    except Exception as e:
                        print(f"Error accessing directory {file_content.path}: {e}")
                        continue
                else:
                    # Check extension
                    _, ext = os.path.splitext(file_content.name)
                    if ext in allowed_extensions:
                        print(f"Processing file: {file_content.path}")
                        try:
                            # Verify if file is text/base64 before decoding
                            if file_content.encoding == "base64":
                                decoded_content = file_content.decoded_content.decode("utf-8")
                            else:
                                continue
                                
                            # Get last commit for this file
                            # Note: This can be slow for many files. Optimizing might be needed.
                            commits = repo.get_commits(path=file_content.path)
                            if commits.totalCount > 0:
                                last_commit = commits[0]
                                commit_msg = last_commit.commit.message
                            else:
                                commit_msg = "Initial"
                            
                            repo_data.append({
                                "file_path": file_content.path,
                                "content": decoded_content,
                                "last_commit": commit_msg
                            })
                            processed_count += 1
                        except Exception as e:
                            print(f"Error processing file {file_content.path}: {e}")
                            
            return repo_data
            
        except Exception as e:
            print(f"Error fetching repo {repo_name}: {e}")
            raise e
