from functools import wraps
from flask import request, jsonify
from core.Configuration.models import User

def admin_api_permission(permLevel):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            apiKey = request.form.get("apiKey")
            if not apiKey or apiKey == "DISABLED":
                return jsonify({"error": "Missing API key"}), 401
            user = User.query.filter(User.apiToken == apiKey).first()  # type: ignore[arg-type]
            print(user)
            if user is None:
                return jsonify({"error": "Invalid API key"}), 401
            if user.permissions < permLevel:
                return jsonify({"error": "Insufficient permissions"}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator