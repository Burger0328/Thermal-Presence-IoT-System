from os.path import isfile
import subprocess
import sys
Import("env")

python = sys.executable

def escape_chars(input_string):
    escaped_string = input_string.replace('"', r'\"').replace("'", r"\'")
    return escaped_string

try:
    subprocess.check_call([python, '-m', 'pip', 'install', 'python-dotenv', '-q'])
except Exception:
    print("Something went wrong when installing python-dotenv")

assert isfile(".env"), "Missing .env file! Copy env.example to .env and fill in your credentials."
try:
    f = open(".env", "r")
    lines = f.readlines()
    envs = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pieces = line.split("=", 1)
        if len(pieces) != 2:
            continue
        envs.append("-D " + pieces[0] + "=" + "'\"{}\"'".format(escape_chars(pieces[1])))
    env.Append(BUILD_FLAGS=envs)
except IOError:
    print("File .env not accessible")
finally:
    f.close()
