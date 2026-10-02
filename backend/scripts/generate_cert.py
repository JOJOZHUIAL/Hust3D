# -*- coding: utf-8 -*-
"""生成自签名 HTTPS 证书（供局域网手机访问以启用摄像头扫码）。

浏览器规定 getUserMedia（摄像头）只能在安全上下文（HTTPS / localhost）使用，
局域网内 http://IP:5000 无法调起摄像头；本脚本生成一张包含本机局域网 IP 的
自签名证书，后端据此在 5443 端口额外提供 HTTPS 服务。

用法：.venv\\Scripts\\python.exe scripts\\generate_cert.py
产物：backend/certs/cert.pem + backend/certs/key.pem（有效期 10 年）
"""
import ipaddress
import os
import socket
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "certs")


def lan_ips():
    """收集本机局域网 IPv4（主出口 IP 优先）。"""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips


def main():
    os.makedirs(CERT_DIR, exist_ok=True)
    cert_path = os.path.join(CERT_DIR, "cert.pem")
    key_path = os.path.join(CERT_DIR, "key.pem")
    if os.path.isfile(cert_path) and os.path.isfile(key_path):
        print(f"证书已存在：{cert_path}")
        print("如局域网 IP 变化导致手机无法访问，删除 certs 目录后重新运行本脚本。")
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    names = [x509.NameAttribute(NameOID.COMMON_NAME, "HUST3D Local Dev")]
    san = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    ips = lan_ips()
    for ip in ips:
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            continue

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name(names))
        .issuer_name(x509.Name(names))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .sign(key, hashes.SHA256())
    )

    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print("HTTPS 证书生成完成：")
    print(f"  证书：{cert_path}")
    print(f"  私钥：{key_path}")
    print(f"  覆盖地址：localhost, 127.0.0.1{', '.join(' ' + ip for ip in ips)}")
    print("重启后端后，局域网手机可通过 https://<电脑IP>:5443 访问并使用摄像头。")


if __name__ == "__main__":
    main()
