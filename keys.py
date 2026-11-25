"""Generate the lab key pair using the installed p and alpha parameters."""

from pathlib import Path
import re
import secrets


def main():
    folder = Path(__file__).resolve().parent
    parameters = (folder / "Pre_installed_CA_information.txt").read_text(
        encoding="utf-8-sig"
    )

    def read_parameter(name):
        match = re.search(
            rf"^{re.escape(name)}\s*=\s*(\d+)\s*$",
            parameters,
            flags=re.MULTILINE,
        )
        if match is None:
            raise ValueError(f"Missing parameter: {name}")
        return int(match.group(1))

    p = read_parameter("p")
    alpha = read_parameter("alpha")
    if p <= 3 or not 1 < alpha < p:
        raise ValueError("Invalid lab parameters p or alpha.")

    private_path = folder / "my_private_key.txt"
    saved = (
        private_path.read_text(encoding="utf-8").strip()
        if private_path.exists()
        else ""
    )
    if saved:
        private_key = int(saved)
        if not 1 <= private_key <= p - 2:
            raise ValueError("Existing private key must be between 1 and p - 2.")
    else:
        # secrets uses the operating system's cryptographic random generator.
        private_key = secrets.randbelow(p - 2) + 1
        private_path.write_text(f"{private_key}\n", encoding="utf-8")

    public_key = pow(alpha, private_key, p)
    public_path = folder / "my_public_key.txt"
    public_path.write_text(f"{public_key}\n", encoding="utf-8")

    print(f"Private key stored in: {private_path.name}")
    print(f"Public key to send to your CA: {public_key}")
    print(f"Public key stored in: {public_path.name}")


if __name__ == "__main__":
    main()
