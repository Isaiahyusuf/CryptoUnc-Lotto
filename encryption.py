# encryption.py - Secure encryption for private keys
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from cryptography.hazmat.backends import default_backend


def _get_encryption_key() -> bytes:
    """
    Derive encryption key from environment variable
    Uses PBKDF2 for key derivation with a salt
    """
    # Get master password from environment
    master_password = os.getenv("ENCRYPTION_KEY", "")
    
    if not master_password:
        raise ValueError(
            "ENCRYPTION_KEY environment variable is required for secure wallet storage. "
            "Please set a strong random key (min 32 characters)."
        )
    
    # Use a fixed salt (in production, this should be per-installation and stored securely)
    # For this bot, we'll derive it from BOT_TOKEN to make it unique per bot
    bot_token = os.getenv("BOT_TOKEN", "")
    salt = base64.b64encode(bot_token[:16].encode()).ljust(16, b'0')[:16]
    
    # Derive a key using PBKDF2
    kdf = PBKDF2(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    
    key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
    return key


def encrypt_private_key(private_key_hex: str) -> str:
    """
    Encrypt a private key hex string
    Returns encrypted string (safe to store in database)
    """
    try:
        key = _get_encryption_key()
        fernet = Fernet(key)
        
        # Encrypt the hex private key
        encrypted = fernet.encrypt(private_key_hex.encode())
        
        # Return as base64 string for storage
        return base64.b64encode(encrypted).decode('utf-8')
    except Exception as e:
        raise RuntimeError(f"Failed to encrypt private key: {str(e)}")


def decrypt_private_key(encrypted_key: str) -> str:
    """
    Decrypt an encrypted private key
    Returns the original hex private key string
    """
    try:
        key = _get_encryption_key()
        fernet = Fernet(key)
        
        # Decode from base64 and decrypt
        encrypted_bytes = base64.b64decode(encrypted_key.encode('utf-8'))
        decrypted = fernet.decrypt(encrypted_bytes)
        
        return decrypted.decode('utf-8')
    except Exception as e:
        raise RuntimeError(f"Failed to decrypt private key: {str(e)}")


def is_encryption_configured() -> bool:
    """Check if encryption is properly configured"""
    try:
        _get_encryption_key()
        return True
    except ValueError:
        return False
