import requests
import sys

def send_heroku_restart():
    """
    Sends a DELETE request to restart dynos for the specified Heroku app.
    Returns a tuple of (status_code, response_headers, response_body, error_message).
    """
    # Define the URL
    url = "https://api.heroku.com/apps/f133b38b-d8d2-465b-8ee8-077c40f36eb9/dynos"

    # Define the headers, excluding HTTP/2 pseudo-headers
    headers = {
        "accept": "application/vnd.heroku+json; version=3.sdk",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "authorization": "Bearer HRKU-AA8J9kOe9TsQTVYn0NcRBqDDy32hEfQkWzjDZqkBiQdAaDMyzwdlWFqXyJyB",
        "cache-control": "no-cache",
        "origin": "https://dashboard.heroku.com",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": "https://dashboard.heroku.com/",
        "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "x-heroku-requester": "dashboard",
        "x-origin": "https://dashboard.heroku.com"
    }

    try:
        print("Sending DELETE request to Heroku API...")
        response = requests.delete(url, headers=headers, timeout=10)
        print(f"Request completed with status code: {response.status_code}")
        return response.status_code, response.headers, response.text, None
    except requests.exceptions.Timeout:
        error_msg = "Request timed out after 10 seconds. Check your internet connection or Heroku API availability."
        print(f"Error: {error_msg}")
        return None, None, None, error_msg
    except requests.exceptions.ConnectionError:
        error_msg = "Failed to connect to the Heroku API. Check your internet connection or the API endpoint."
        print(f"Error: {error_msg}")
        return None, None, None, error_msg
    except requests.exceptions.HTTPError as http_err:
        error_msg = f"HTTP Error occurred: {http_err}"
        print(f"Error: {error_msg}")
        return None, None, None, error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"Error sending request: {e}"
        print(f"Error: {error_msg}")
        return None, None, None, error_msg

def handle_command(command):
    """
    Handles incoming commands. If the command is '/restart', sends the Heroku restart request.
    Returns a response message.
    """
    if not isinstance(command, str):
        return "Error: Command must be a string."

    command = command.strip().lower()
    if command != "/restart":
        return "Unknown command. Use /restart to restart Heroku dynos."

    status_code, headers, body, error = send_heroku_restart()
    
    if error:
        return f"Failed to restart dynos: {error}"
    
    if status_code == 202:
        rate_limit = headers.get('ratelimit-remaining', 'Not provided')
        return f"Dynos restarted successfully! Rate Limit Remaining: {rate_limit}"
    
    return f"Failed to restart dynos: Status {status_code}, Response: {body}"

# Example usage for testing
if __name__ == "__main__":
    # Simulate a command
    test_command = "/restart"
    print(f"Testing command: {test_command}")
    result = handle_command(test_command)
    print(result)

    # Test an invalid command
    test_command = "/invalid"
    print(f"\nTesting command: {test_command}")
    result = handle_command(test_command)
    print(result)
