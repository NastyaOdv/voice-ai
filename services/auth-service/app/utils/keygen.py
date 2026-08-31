"""Generate the RS256 key pair used to sign JWTs, if it does not exist yet.

Run at container start (see entrypoint.sh). In production the keys would come from
a secret manager; for local dev we generate them once into a mounted volume.
"""
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.conf.config import get_settings


def generate_keys_if_missing() -> None:
    settings = get_settings()
    private_path = Path(settings.jwt_private_key_path)
    public_path = Path(settings.jwt_public_key_path)
    if private_path.exists() and public_path.exists():
        return

    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


if __name__ == "__main__":
    generate_keys_if_missing()
    print("[keygen] RS256 keys ready")
