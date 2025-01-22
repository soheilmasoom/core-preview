
import os
import base64
import xml.etree.ElementTree as ET
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


def int_to_base64(n):
    """
    Converts an integer to a big-endian byte array and encodes it in base64.
    """
    byte_length = (n.bit_length() + 7) // 8
    return base64.b64encode(n.to_bytes(byte_length, 'big')).decode('utf-8')


def export_private_key_to_xml(private_key):
    """
    Exports the private key to XML format similar to RSACryptoServiceProvider.ToXmlString(true).
    """
    numbers = private_key.private_numbers()
    xml_root = ET.Element('RSAKeyValue')

    ET.SubElement(xml_root, 'Modulus').text = int_to_base64(numbers.public_numbers.n)
    ET.SubElement(xml_root, 'Exponent').text = int_to_base64(numbers.public_numbers.e)
    ET.SubElement(xml_root, 'P').text = int_to_base64(numbers.p)
    ET.SubElement(xml_root, 'Q').text = int_to_base64(numbers.q)
    ET.SubElement(xml_root, 'DP').text = int_to_base64(numbers.dmp1)
    ET.SubElement(xml_root, 'DQ').text = int_to_base64(numbers.dmq1)
    ET.SubElement(xml_root, 'InverseQ').text = int_to_base64(numbers.iqmp)
    ET.SubElement(xml_root, 'D').text = int_to_base64(numbers.d)

    return ET.tostring(xml_root, encoding='utf-8', method='xml').decode('utf-8')


def export_public_key_to_xml(public_key):
    """
    Exports the public key to XML format similar to RSACryptoServiceProvider.ToXmlString(false).
    """
    numbers = public_key.public_numbers()
    xml_root = ET.Element('RSAKeyValue')

    ET.SubElement(xml_root, 'Modulus').text = int_to_base64(numbers.n)
    ET.SubElement(xml_root, 'Exponent').text = int_to_base64(numbers.e)

    return ET.tostring(xml_root, encoding='utf-8', method='xml').decode('utf-8')


def generate_sepah_private_keys():
    try:
        # Generate RSA private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        public_key = private_key.public_key()

        # Export keys to XML
        private_key_xml = export_private_key_to_xml(private_key)
        public_key_xml = export_public_key_to_xml(public_key)

        # Define file paths
        private_key_path = "PrivateKey.xml"
        public_key_path = "PublicKey.xml"

        # Write keys to files
        with open(private_key_path, "w") as priv_file:
            priv_file.write(private_key_xml)

        with open(public_key_path, "w") as pub_file:
            pub_file.write(public_key_xml)

        # Get absolute paths
        private_key_full_path = os.path.abspath(private_key_path)
        public_key_full_path = os.path.abspath(public_key_path)

        # Print success messages
        print("Private and public keys have been generated and saved successfully.")
        print(f"Private Key Path: {private_key_full_path}")
        print(f"Public Key Path: {public_key_full_path}")

    except Exception as ex:
        print(f"Error: {ex}")
