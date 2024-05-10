### Observations and Suggestions

#1. **User-Friendly Error Messages:**
#   - Some errors could be more user-friendly, especially when the JSON parsing fails or the assistant encounters an unknown error.
#
#    **Solution:**
#    Add more specific error handling and provide meaningful tips to the user.
#
#   
#2. **Provide Clear Command Execution Feedback:**
#   - Clearly distinguish between successful and unsuccessful command execution.
#   - Provide feedback if a command is not recognized due to shell differences.
#
#    **Solution:**
#    Add specific messages for successful execution and unrecognized commands.
#
#   
#
#3. **Cross-Platform Compatibility:**
#   - Some commands and programs are platform-specific (e.g., `open` on macOS vs. `xdg-open` on Linux).
#   - Ensure the assistant generates appropriate commands for the detected platform.
#
#    **Solution:**
#    Modify the system prompt to inform the model of platform-specific details and handle platform-specific command adjustments.
#
#  
#4. **Logging Mechanism:**
#   - Keeping logs could help users debug issues and provide feedback.
#
#    **Solution:**
#    Implement a simple logging mechanism.
#
# 
#5. **Command Context Suggestions:**
#   - The assistant could suggest recent similar commands when it detects a repeated user query pattern.
#
#    **Solution:**
#    Add a function to suggest recently used commands.
#
# 
#6. **Customizable History Length:**
#   - Allow users to customize the command history length.
#
#    **Solution:**
#    Add a constant to control the history length.

import os
import shlex
from pathlib import Path
from dotenv import load_dotenv
import subprocess
import traceback
import json
from groq import Groq
import platform
import logging

# Setup logging
logging.basicConfig(filename='assistant.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize an empty list to keep the history of commands and their contexts
command_history = []
COMMAND_HISTORY_LENGTH = 10

# Detect shell and operating system
def detect_shell_and_os():
    """Detect the current shell and operating system."""
    # Detect the shell
    shell = os.getenv('SHELL', '/bin/bash')
    shell_name = os.path.basename(shell)

    # Detect the OS
    operating_system = platform.system().lower()

    return shell_name, operating_system

def execute_command(command):
    """Execute a shell command and return the output and exit code."""
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        stdout, stderr = process.communicate()
        exit_code = process.wait()
        return stdout.decode().strip(), stderr.decode().strip(), exit_code
    except Exception as e:
        return "", str(e), 1

def check_program_installed(program: str) -> bool:
    """Check if a particular program is installed and available."""
    return subprocess.call(['which', program], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

def provide_helpful_tips(command: str, stderr: str) -> str:
    """Provide tips or suggestions when a command fails."""
    if "ls:" in stderr and "No such file or directory" in stderr:
        return f"Tip: The directory in the command '{command}' does not exist. Please check the path."
    if "command not found" in stderr:
        program = command.split()[0]
        return f"Tip: The command '{program}' is not available. Please install it or check your spelling."
    return stderr

def update_command_history(user_prompt, command, success, output=None, error=None):
    command_history.append({
        'user_prompt': user_prompt,
        'command': command,
        'success': success,
        'output': output,
        'error': error
    })
    # Keep only the last N commands in memory to avoid unbounded growth
    if len(command_history) > COMMAND_HISTORY_LENGTH:
        command_history.pop(0)

    log_command(user_prompt, command, success, output, error)

def log_command(user_prompt, command, success, output=None, error=None):
    """Log command execution results."""
    result = "Success" if success else "Error"
    logging.info(f"User Prompt: {user_prompt}, Command: {command}, Result: {result}, Output: {output}, Error: {error}")

def generate_system_prompt(shell_name, operating_system):
    """Generate the system prompt, incorporating command history and environment information."""
    platform_info = {
        "macos": {
            "open_command": "open",
            "browser": "Safari"
        },
        "linux": {
            "open_command": "xdg-open",
            "browser": "firefox"
        },
        "windows": {
            "open_command": "start",
            "browser": "Microsoft Edge"
        }
    }

    platform_data = platform_info.get(operating_system, {})
    history_info = '\n'.join([
        f"Previous Command: {h['command']}, Success: {h['success']}, Error: {h['error'] or 'None'}"
        for h in command_history[-3:]
    ])  # Last 3 commands

    system_prompt = f"""You are an AI assistant that can understand natural language prompts and generate the appropriate shell commands to execute based on the user's request. Your task is to analyze the user's input and determine the best command to execute, then provide the command in a valid JSON format with a "command" key.

Environment Information:
- Shell: {shell_name}
- Operating System: {operating_system}
- Open Command:Continuing from where the script left off:

```python
- Open Command: {platform_data.get("open_command", "unknown")}
- Default Browser: {platform_data.get("browser", "unknown")}

{history_info}

Please be concise and only provide the necessary command, without any additional explanation or context. Your goal is to provide the most appropriate command for the user's request.
"""
    return system_prompt

def handle_error_and_retry(user_prompt, error_message, shell_name, operating_system):
    """Handle errors by requesting a new command based on the error message."""
    retry_prompt = f"The last command failed with the following error: {error_message}. Please modify the command to fix the error."
    system_prompt = generate_system_prompt(shell_name, operating_system)
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": retry_prompt}
        ],
        model="mixtral-8x7b-32768",
        temperature=0.1,
        max_tokens=32768,
        response_format={"type": "json_object"}
    )

    response_json = chat_completion.choices[0].message.content
    try:
        command_dict = json.loads(response_json)
        command = command_dict['command']
        print(f"Retrying command [{command}] ...")
        stdout, stderr, exit_code = execute_command(command)

        if exit_code == 0:
            update_command_history(user_prompt, command, True, stdout)
            print("Command executed successfully.")
            print("Command output:")
            print(stdout)
        else:
            helpful_tips = provide_helpful_tips(command, stderr)
            update_command_history(user_prompt, command, False, error=helpful_tips)
            print("Error executing command:")
            print(helpful_tips)
    except json.JSONDecodeError as e:
        print(f"Error parsing response as JSON: {e}")
        print(f"Response JSON: {response_json}")
        print("Tip: Please ensure your input is clear, or try simplifying your request.")
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        print("Tip: An unexpected error occurred. Please try again.")

def suggest_similar_commands(user_prompt):
    """Suggest similar commands based on previous commands."""
    suggestions = [h['command'] for h in command_history if user_prompt.lower() in h['user_prompt'].lower()]
    if suggestions:
        print("Did you mean one of these commands?")
        for i, suggestion in enumerate(suggestions, 1):
            print(f"{i}. {suggestion}")

# Activate the virtual environment
venv_path = '/Users/Shared/Relocated Items/Docs_dump/visual studio code projects/CLI_assistant/my_env'
activate_script = os.path.join(venv_path, 'bin', 'activate')
activate_script = shlex.quote(activate_script)
subprocess.run(f'source {activate_script}', shell=True, check=True)

# Load environment variables
env_path = Path('/Users/Shared/Relocated Items/Docs_dump/visual studio code projects/CLI_assistant/.env')
load_dotenv(dotenv_path=env_path)

try:
    load_dotenv() 
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found in environment variables.")

    client = Groq(api_key=api_key)

    shell_name, operating_system = detect_shell_and_os()

    while True:
        user_prompt = input("Query:> ")

        # Exit check
        if user_prompt.lower().strip() in ['exit', 'quit']:
            break

        # Suggest similar commands
        suggest_similar_commands(user_prompt)

        system_prompt = generate_system_prompt(shell_name, operating_system)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="mixtral-8x7b-32768",
            temperature=0.1,
            max_tokens=32768,
            response_format={"type": "json_object"}
        )

        response_json = chat_completion.choices[0].message.content

        try:
            command_dict = json.loads(response_json)
            command = command_dict['command']
            print(f"Running command [{command}] ...")
            stdout, stderr, exit_code = execute_command(command)

            if exit_code == 0:
                update_command_history(user_prompt, command, True, stdout)
                print("Command executed successfully.")
                print("Command output:")
                print(stdout)
            else:
                helpful_tips = provide_helpful_tips(command, stderr)
                update_command_history(user_prompt, command, False, error=helpful_tips)
                print("Error executing command:")
                print(helpful_tips)
                handle_error_and_retry(user_prompt, helpful_tips, shell_name, operating_system)
        except json.JSONDecodeError as e:
            print(f"Error parsing response as JSON: {e}")
            print(f"Response JSON: {response_json}")
            print("Tip: Please ensure your input is clear, or try simplifying your request.")
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()
            print("Tip: An unexpected error occurred. Please try again.")

except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
