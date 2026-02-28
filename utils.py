import json

def load_data():
    with open("storage.json", "r") as f:
        return json.load(f)

def save_data(data):
    with open("storage.json", "w") as f:
        json.dump(data, f, indent=4)

def get_user(user_id):
    data = load_data()
    return data["users"].get(str(user_id), None)

def set_user(user_id, user_data):
    data = load_data()
    data["users"][str(user_id)] = user_data
    save_data(data)

def add_to_queue(user_id):
    data = load_data()
    if user_id not in data["queue"]:
        data["queue"].append(user_id)
        save_data(data)

def remove_from_queue(user_id):
    data = load_data()
    if user_id in data["queue"]:
        data["queue"].remove(user_id)
        save_data(data)

def match_users():
    data = load_data()
    queue = data["queue"]
    if len(queue) >= 2:
        user1, user2 = queue[0], queue[1]
        data["users"][str(user1)]["partner"] = user2
        data["users"][str(user2)]["partner"] = user1
        data["queue"] = queue[2:]
        save_data(data)
        return user1, user2
    return None, None
