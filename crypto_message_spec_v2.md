# Crypto Server — Message Format Specification (v2)

For developers writing their own client for the crypto server. Any language works. You need only a TCP socket library, a JSON library, base64, an AES-256-GCM implementation, and SHA-256.

**What is new in v2:** the `verify_hmac` command and the course HMAC algorithm (sections 4.1, 4.2, 6). Everything else is unchanged from v1.

Your instructor will give you: the **server IP address**, the **port** (normally `8080`), and your **username**.

> **Teaching server.** Keys and files cross the network unencrypted, and your username is the only credential. Do not send real secrets.

## 1. What the server does

| Command | What it does |
|---|---|
| `get_key` | Returns a new random 256-bit AES key. The server does not remember it. |
| `decrypt` | You send an encrypted file and its key; the server returns the decrypted file. |
| `verify_hmac` | You send a file, a key and an HMAC computed by your client; the server checks the HMAC and answers `VERIFIED` or `FAILED`. |

**Encryption is done by your client, locally.** The server never encrypts. The normal workflow:

1. Send `get_key`, receive a key.
2. Encrypt your file locally with that key (format in section 5), and save the key beside the encrypted file.
3. Later, send `decrypt` with the encrypted file and the key; receive the original file back.

**The HMAC is also computed by your client, locally.** The workflow:

1. Send `get_key`, receive a key K.
2. Compute the HMAC of a file with K (algorithm in section 6) and save the HMAC and K beside the file.
3. Later, send `verify_hmac` with the file, K and the HMAC; the server tells you whether they match.

The two workflows are independent. The HMAC can be computed over any file.

## 2. Transport

- Plain **TCP**. Not HTTP, not TLS, not WebSocket.
- Default port **8080**.
- The server handles many clients at once.
- **Idle timeout: 60 seconds.** If the server receives no bytes from you for 60 seconds it closes the connection. The timer restarts whenever any data arrives.
- Recommended pattern: **one connection per request.** Connect, send one message, read one reply, close.

## 3. Message framing

Every message in both directions is exactly this, in order:

```
+----------------------+---------------------------+----------------------+
| 4 bytes              | header_len bytes          | payload_len bytes    |
| header_len           | header                    | payload              |
| unsigned, BIG-endian | UTF-8 JSON object         | raw binary (optional)|
+----------------------+---------------------------+----------------------+
```

- `header_len` is the byte length of the JSON header only. It is **big-endian**, unsigned, 4 bytes. It does not include itself or the payload.
- The header is one JSON **object**, UTF-8 encoded, **at most 1000 bytes**.
- `payload_len` is a field inside the header. If it is `0` or missing there is no payload. Otherwise exactly that many raw bytes follow the header.
- The 1000-byte limit applies to the header only. The payload is limited separately (section 8).

TCP is a byte stream. One `recv()` call may return less than you asked for. **Always loop until you have read exactly the number of bytes you need.**

## 4. Messages

### 4.1 Requests (client → server)

All requests need these header fields:

| Field | Type | Meaning |
|---|---|---|
| `type` | string | Command: `"get_key"`, `"decrypt"` or `"verify_hmac"` |
| `username` | string | Your assigned username. 1–32 characters from `A-Z a-z 0-9 _ . -`. Case-sensitive. |
| `payload_len` | integer ≥ 0 | Byte length of the payload that follows. Use `0` when there is none. |

**`get_key`**: no other fields, no payload.

```json
{"type":"get_key","username":"student01","payload_len":0}
```

**`decrypt`**: one extra field, plus the payload.

| Field | Type | Meaning |
|---|---|---|
| `key` | string | The 32-byte AES key, **standard base64** (with `=` padding), 44 characters |

The payload is the encrypted file in the format of section 5, exactly as saved by your client.

```json
{"type":"decrypt","username":"student01","key":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=","payload_len":39}
```

**`verify_hmac`**: two extra fields, plus the payload.

| Field | Type | Meaning |
|---|---|---|
| `key` | string | The 32-byte key K, standard base64 (44 characters) |
| `hmac` | string | The 32-byte HMAC value you computed, standard base64 (44 characters) |

The payload is the file the HMAC was computed over, exactly as it is on disk.

```json
{"type":"verify_hmac","username":"student01","key":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=","hmac":"WFxl5t64uHbtdCIsWWQGDnBxkt+M6bkbYZjeFz+//y4=","payload_len":11}
```

### 4.2 Replies (server → client)

The reply uses the same framing.

| `type` | Extra fields | Payload |
|---|---|---|
| `key_result` | `key`: base64 of the new 32-byte key | none |
| `decrypt_result` | none | the decrypted file bytes |
| `verify_result` | `result`: `"VERIFIED"` or `"FAILED"` | none |
| `error` | `detail`: text | none |

Replies also contain `payload_len`. Read it, and then read exactly that many payload bytes.

```json
{"type":"key_result","key":"<44 base64 chars>","payload_len":0}
{"type":"decrypt_result","payload_len":11}
{"type":"verify_result","result":"VERIFIED","payload_len":0}
{"type":"verify_result","result":"FAILED","payload_len":0}
{"type":"error","detail":"error processing request","payload_len":0}
```

### 4.3 Errors

The server uses **one generic error** for every failure and gives no reason. Possible causes:

- username not recognized, or not 1–32 allowed characters
- unknown or unsupported `type`
- header too long, not valid JSON, or missing/invalid fields
- payload larger than the limit
- wrong key, key not 32 bytes, or a file that was modified or corrupted (`decrypt`)
- `verify_hmac` with a missing `key` or `hmac`, or one that is not valid base64 or does not decode to exactly 32 bytes

After an error the server may close the connection. Treat `error` as the end of that exchange.

**A failed verification is not an error.** If a `verify_hmac` request is well formed but the HMAC does not match the file and key, the server replies with `verify_result` and `"result":"FAILED"`. Only a badly formed request gets `error`. Your client should show these two outcomes differently, so a failed check isn't confused with a bad request.

## 5. Encrypted file format

AES-256 in **GCM** mode with these exact conventions:

```
| 12-byte nonce | ciphertext | 16-byte GCM tag |
```

- **Key**: 32 random bytes (from `get_key`).
- **Nonce**: 12 random bytes, a new one for every file. Stored as the **first 12 bytes** of the encrypted file.
- **Ciphertext**: same length as the plaintext.
- **Tag**: 16 bytes, stored **last**, immediately after the ciphertext.
- **Associated data (AAD)**: none (empty).
- Total size is the plaintext size + 28 bytes.

Most libraries (Python `cryptography`'s `AESGCM`, Java `AES/GCM/NoPadding`, Node `crypto`, Go `cipher.NewGCM`) return `ciphertext || tag` already joined. In that case you only need to put the nonce in front. Some libraries (Node, for example) give the tag separately, so you must append it yourself.

### Key file convention

Save the key next to the encrypted file, with the same base name and a `.key` extension. The file contains the key as the same base64 text used on the wire:

```
report.txt        original file
report.txt.enc    encrypted file
report.txt.key    key, base64 text
```

This is what the instructor's reference client does. Following it lets your files work with other clients.

## 6. The HMAC algorithm

This is a **course-specific design. It is not standard HMAC (RFC 2104).** Its output does not match Python's `hmac` module, OpenSSL, or any other standard HMAC library, so do not use one. Implement it exactly as written, using only a SHA-256 hash.

- **Hash:** SHA-256.
- **Key K:** the 32-byte key returned by `get_key`.
- **Derived keys**, each the same length as K (32 bytes), with **no block padding**:
  - `Ki = K XOR 0x36 0x36 ... 0x36` (32 bytes of `0x36`)
  - `Ko = K XOR 0x5c 0x5c ... 0x5c` (32 bytes of `0x5c`)
- **For a file whose contents are the byte string x:**

  ```
  HMAC = SHA-256( Ko || SHA-256( Ki || x ) )
  ```

  `||` is byte concatenation. The inner hash is the **32 raw bytes**, not hex text. The result is 32 bytes.

Python, for reference:

```python
def custom_hmac(key, data):                    # key is 32 bytes
    ki = bytes(b ^ 0x36 for b in key)
    ko = bytes(b ^ 0x5C for b in key)
    return sha256(ko + sha256(ki + data))      # sha256() returns the 32-byte digest
```

On the wire, K and the HMAC are both sent as standard base64.

### Local file convention

Save the results next to the file, as base64 text, like the AES key files:

```
report.txt           the file
report.txt.hmac      the 32-byte HMAC, base64 text
report.txt.hmackey   the key K, base64 text
```

## 7. Typical exchanges

**Get a key**

```
client -> server:  [len][{"type":"get_key","username":"u","payload_len":0}]
server -> client:  [len][{"type":"key_result","key":"...","payload_len":0}]
client closes the connection
```

**Verify an HMAC**

```
client -> server:  [len][{"type":"verify_hmac","username":"u","key":"...","hmac":"...","payload_len":N}][N bytes]
server -> client:  [len][{"type":"verify_result","result":"VERIFIED","payload_len":0}]
client closes the connection
```

**Decrypt a file**

```
client -> server:  [len][{"type":"decrypt","username":"u","key":"...","payload_len":N}][N bytes]
server -> client:  [len][{"type":"decrypt_result","payload_len":M}][M bytes]
client closes the connection
```

Send the header and payload straight after each other. There is no separate "ready" step.

## 8. Limits

| Limit | Value |
|---|---|
| Header size | 1000 bytes |
| Payload size | 1,048,576 bytes (1 MiB) (also the largest file for `verify_hmac`) |
| Largest plaintext you can encrypt | 1,048,548 bytes (1 MiB − 28) |
| Idle timeout | 60 seconds with no bytes received |

The server checks `payload_len` before reading the payload. If it is over the limit, the server answers with `error` and closes the connection, so a client may see its send fail with a connection reset. Check the file size before sending.

## 9. Test vectors

Use these to check your implementation before touching the real server.

**Framing of a `get_key` request.** The header is the 57 bytes of compact JSON below. The 4-byte length prefix is `00 00 00 39`.

```
header (57 bytes): {"type":"get_key","username":"student01","payload_len":0}
full message hex:  000000397b2274797065223a226765745f6b6579222c22757365726e616d65223a2273747564656e743031222c227061796c6f61645f6c656e223a307d
```

Spaces inside the JSON are allowed, so the exact bytes may differ. The length prefix must match whatever you send.

**AES-GCM.**

```
key (hex):      000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f
key (base64):   AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=
nonce (hex):    000102030405060708090a0b
plaintext:      hello world   (ASCII, 11 bytes)
encrypted file (hex, 39 bytes):
000102030405060708090a0b2f67ba77aac5b574ff2df305301c56437e2377b98ef3961c271928
```

If your code encrypts `hello world` with that key and nonce and produces those 39 bytes, your file format is correct. The server accepts any file encrypted the right way, with any nonce, so you can also send this file with this key as a `decrypt` request. The reply payload should be `hello world`.

**HMAC** (algorithm of section 6; K = the same 32 bytes `00 01 02 ... 1f` as the AES key above).

```
K (base64):  AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=
Ki (hex):    36373435323330313e3f3c3d3a3b383926272425222320212e2f2c2d2a2b2829
Ko (hex):    5c5d5e5f58595a5b54555657505152534c4d4e4f48494a4b4445464740414243

x = "hello world" (ASCII, 11 bytes)
  inner = SHA-256(Ki || x) (hex): 05001c1f5260531db22d744e1629e7450903558c545cdd514bea3f555684deac
  HMAC (hex):    585c65e6deb8b876ed74222c5964060e707192df8ce9b91b6198de173fbfff2e
  HMAC (base64): WFxl5t64uHbtdCIsWWQGDnBxkt+M6bkbYZjeFz+//y4=

x = empty file (0 bytes)
  HMAC (hex):    bb7a30c41398c718904264ee91bc9ea48a36493f9e5a5577f53a1408a6ffa5b3
```

If your code produces `411b9a51e8565e1fc79643b2a6c4672f4a3c3e573c33d0995a08748cb6128e8e` for the first one, you used a standard HMAC library. That is wrong for this course; implement section 6 by hand.

Once your HMAC code matches those values, send a `verify_hmac` request with K, the HMAC value above (base64) and the 11-byte file `hello world`. The server should reply `VERIFIED`. Change one byte of the file and it should reply `FAILED`.

## 10. Reference snippet (Python 3.9+)

```python
import base64, json, os, socket, struct
from cryptography.hazmat.primitives.ciphers.aead import AESGCM   # pip install cryptography

def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("connection closed")
        buf += chunk
    return buf

def exchange(host, port, header, payload=b""):
    with socket.create_connection((host, port), timeout=30) as s:
        header = dict(header, payload_len=len(payload))
        hb = json.dumps(header).encode("utf-8")
        s.sendall(struct.pack(">I", len(hb)) + hb + payload)
        (rlen,) = struct.unpack(">I", recv_exact(s, 4))
        reply = json.loads(recv_exact(s, rlen))
        data = recv_exact(s, reply.get("payload_len", 0))
        return reply, data

def get_key(host, port, user):
    reply, _ = exchange(host, port, {"type": "get_key", "username": user})
    if reply["type"] != "key_result":
        raise RuntimeError("server error")
    return base64.b64decode(reply["key"])

def encrypt(key, plaintext):
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)

def sha256(data):
    from cryptography.hazmat.primitives import hashes
    h = hashes.Hash(hashes.SHA256())
    h.update(data)
    return h.finalize()

def custom_hmac(key, data):                      # section 6; NOT standard HMAC
    ki = bytes(b ^ 0x36 for b in key)
    ko = bytes(b ^ 0x5C for b in key)
    return sha256(ko + sha256(ki + data))

def verify_on_server(host, port, user, key, mac, data):
    hdr = {"type": "verify_hmac", "username": user,
           "key": base64.b64encode(key).decode(), "hmac": base64.b64encode(mac).decode()}
    reply, _ = exchange(host, port, hdr, data)
    if reply["type"] != "verify_result":
        raise RuntimeError("server error")        # bad request, not a failed check
    return reply["result"] == "VERIFIED"

def decrypt_on_server(host, port, user, key, blob):
    hdr = {"type": "decrypt", "username": user, "key": base64.b64encode(key).decode()}
    reply, data = exchange(host, port, hdr, blob)
    if reply["type"] != "decrypt_result":
        raise RuntimeError("server error")
    return data
```

## 11. Notes for using an AI coding assistant (such as Claude Code)

Put this file in your project folder, and tell the assistant to read it first (for example, "Read crypto_message_spec_v1.md and implement a client for it"). A few things make that go faster and more reliably.

**Give it what it needs up front.**
- The spec file, your server IP, port, and username. Keep the username out of any shared repo.
- The language and UI toolkit you want, and that the app should run on your own computer.
- Ask it to implement the spec exactly, and to ask you a question rather than guess when something is unclear.

**Ask it to build in this order, testing each step.**
1. Framing and `recv_exact` (section 3), tested with the framing vector in section 9.
2. AES-GCM encrypt, tested against the test vector in section 9. Do this before any networking.
3. `get_key` against the real server.
4. A full encrypt-then-`decrypt` round trip, then compare the output file to the original byte for byte.
5. The HMAC function, tested against the HMAC vectors in section 9 before any networking, then a `verify_hmac` round trip: it should say `VERIFIED`, and `FAILED` after you change a byte of the file.

**Ask it to write a local fake server** that speaks this protocol on `127.0.0.1`, so it can test your client without the real server or network. A fake server only needs to implement section 3 and echo canned replies. It can also implement the section 6 HMAC check using the same code as your client, which proves your client and fake server agree but not that they are correct, so always check against the section 9 vectors too.

**Common mistakes to tell it to avoid:**
- Using little-endian or the wrong width for the 4-byte length prefix. It is big-endian, 4 bytes.
- Reading with a single `recv()` instead of looping until all bytes arrive.
- Counting characters instead of bytes for `header_len`.
- URL-safe base64. Use standard base64 with `=` padding.
- Putting the nonce or tag in the wrong place, or adding AAD.
- Reusing a nonce. Generate a fresh random 12 bytes per file.
- Using a standard HMAC library (`hmac`, OpenSSL, `crypto.createHmac`, ...) for the HMAC. It must be the section 6 algorithm. Also avoid padding K to 64 bytes: the derived keys are 32 bytes.
- Hashing hex text instead of raw bytes for the inner hash, or XOR-ing with the wrong constant (`0x36` for Ki, `0x5c` for Ko).
- Treating `verify_result` with `FAILED` as a program error. It is a valid answer meaning the HMAC doesn't match.
- Forgetting `payload_len` in the header, or setting it to a wrong value.
- Doing network calls on a UI thread, which freezes the window.
- Printing or logging keys.

**When something fails**, the server error is deliberately vague, so don't ask the assistant to guess from it. Instead, have it check each part separately: does the framing match the vector, does the encrypted file match the test vector, does a file produced by your client decrypt locally with a standard tool. Then look at the connection, the username, and the file size.

## 12. Compliance checklist

- [ ] 4-byte big-endian length, then JSON header of at most 1000 bytes
- [ ] header always has `type`, `username`, `payload_len`
- [ ] receive loops read exactly the stated byte counts
- [ ] `decrypt` sends the key as standard base64 in the header and the encrypted file as the payload
- [ ] `verify_hmac` sends `key` and `hmac` as standard base64 in the header and the file as the payload
- [ ] HMAC follows section 6 exactly and matches the section 9 vectors
- [ ] `verify_result` `FAILED` is shown differently from an `error` reply
- [ ] encrypted file is `nonce(12) | ciphertext | tag(16)`, with no AAD
- [ ] files over the size limit are refused before sending
- [ ] `error` replies and connection failures are shown clearly to the user
- [ ] the key is never shown or logged
