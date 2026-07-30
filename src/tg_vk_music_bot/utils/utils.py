import os

from OpenSSL import crypto


# self-ssl
def create_self_signed_cert(network_config, ssl_config):
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 1024)  # размер может быть 2048, 4196

    #  Создание сертификата
    cert = crypto.X509()
    cert.get_subject().C = "RU"  # указываем свои данные
    cert.get_subject().ST = "Saint-Petersburg"
    cert.get_subject().L = "Saint-Petersburg"  # указываем свои данные
    cert.get_subject().O = "pff"  # указываем свои данные
    cert.get_subject().CN = network_config['domen']  # указываем свои данные
    cert.set_serial_number(1)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(365 * 24 * 60 * 60)  # срок "жизни" сертификата
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, b'SHA256')

    with open(os.path.join(ssl_config['dir'], ssl_config['cert_filename']), "w") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("ascii"))

    with open(os.path.join(ssl_config['dir'], ssl_config['key_filename']), "w") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k).decode("ascii"))

    return crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("ascii")