import requests

url = f"https://api.telegram.org/bot8790276673:AAH2hZgRa6n3zTgrPar6DfOkkUlVM2WhBKA/getMe"
response = requests.get(url)
print(response.json())