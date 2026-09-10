# 输入示例：Python用户注册接口代码

## 用户描述
"帮我看看这段Python代码有没有问题，是用户注册接口。"

## 代码内容

```python
from flask import Flask, request, jsonify
import hashlib
import sqlite3

app = Flask(__name__)
DB_PATH = "users.db"

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data['username']
    password = data['password']
    email = data['email']

    # 检查用户名是否已存在
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    if cursor.fetchone():
        return jsonify({"error": "Username already exists"}), 400

    # 使用MD5加密密码
    hashed = hashlib.md5(password.encode()).hexdigest()

    # 插入用户
    insert_query = "INSERT INTO users (username, password, email) VALUES ('" + username + "', '" + hashed + "', '" + email + "')"
    cursor.execute(insert_query)
    conn.commit()
    conn.close()

    return jsonify({"message": "User registered successfully"}), 201

if __name__ == '__main__':
    app.run(debug=True)
```

## 已知上下文
- Flask Web应用
- SQLite数据库
- 用户注册功能
