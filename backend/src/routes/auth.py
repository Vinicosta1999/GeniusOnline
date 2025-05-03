# -*- coding: utf-8 -*-
import logging
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
# from flask_login import LoginManager, login_user, logout_user, login_required, current_user # Replaced by JWT
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, JWTManager
from src.models.user import db, User

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# # Configure Flask-Login (Removed)
# login_manager = LoginManager()

# @login_manager.user_loader
# def load_user(user_id):
#     """Flask-Login user loader callback."""
#     return User.query.get(int(user_id))

# Configure JWTManager (Initialization moved to main.py, but keep reference)
# jwt = JWTManager() # Initialized in main.py

@auth_bp.route("/register", methods=["POST"])
def register():
    """Handles user registration and returns JWT tokens."""
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"message": "Nome de usuário e senha são obrigatórios."}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"message": "Nome de usuário já existe."}), 409

    hashed_password = generate_password_hash(password, method="pbkdf2:sha256")
    new_user = User(username=username, password_hash=hashed_password)
    
    try:
        db.session.add(new_user)
        db.session.commit()
        logger.info(f"User {username} registered successfully.")
        
        # Generate tokens for the new user
        access_token = create_access_token(identity=new_user.id)
        refresh_token = create_refresh_token(identity=new_user.id)
        
        return jsonify({
            "message": "Registro bem-sucedido!",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {"id": new_user.id, "username": new_user.username}
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error registering user {username}: {e}")
        return jsonify({"message": "Erro ao registrar usuário."}), 500

@auth_bp.route("/login", methods=["POST"])
def login():
    """Handles user login and returns JWT tokens."""
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"message": "Nome de usuário e senha são obrigatórios."}), 400

    user = User.query.filter_by(username=username).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"message": "Credenciais inválidas."}), 401

    # Generate tokens
    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)
    
    logger.info(f"User {username} logged in successfully.")
    return jsonify({
        "message": "Login bem-sucedido!",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {"id": user.id, "username": user.username}
    }), 200

# @auth_bp.route("/logout", methods=["POST"])
# @login_required # Replaced by JWT
# def logout():
#     """Handles user logout."""
#     # username = current_user.username # No current_user with JWT stateless approach
#     # logout_user() # Clears the user session
#     # logger.info(f"User {username} logged out.")
#     # Logout is typically handled client-side by removing the token.
#     # For added security, can implement token blocklisting.
#     return jsonify({"message": "Logout bem-sucedido! (Token deve ser removido no cliente)"}), 200

@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True) # Requires a valid refresh token
def refresh():
    """Refreshes the access token using a refresh token."""
    current_user_id = get_jwt_identity()
    new_access_token = create_access_token(identity=current_user_id)
    logger.info(f"Access token refreshed for user ID {current_user_id}.")
    return jsonify({"access_token": new_access_token}), 200

@auth_bp.route("/status", methods=["GET"])
@jwt_required() # Requires a valid access token
def status():
    """Checks if the user is currently logged in via JWT."""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    if not user:
         # Should not happen if JWT is valid, but good practice
         return jsonify({"message": "Usuário não encontrado."}), 404
         
    return jsonify({
        "logged_in": True,
        "user": {"id": user.id, "username": user.username}
    }), 200

# @login_manager.unauthorized_handler # Removed
# def unauthorized():
#     """Handles unauthorized access attempts."""
#     return jsonify({"message": "Autenticação necessária."}), 401

# JWTManager error handlers can be added here or in main.py
# e.g., @jwt.unauthorized_loader, @jwt.invalid_token_loader

