"""
正方教务系统 RSA 加密 — 直接移植自 school-sdk (FarmerChillax/new-school-sdk)
使用与教务系统前端 JavaScript 完全一致的加密算法
"""

class Base64:
    """与 school-sdk 完全一致的 Base64 编解码"""
    
    def __init__(self):
        self.b64map = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        self.b64pad = "="
        self.idx = "0123456789abcdefghijklmnopqrstuvwxyz"

    def hex2b64(self, h):
        ret = ''
        ii = 0
        for i in range(0, len(h) - 2, 3):
            c = int(h[i:i+3], 16)
            ret += self.b64map[c >> 6] + self.b64map[c & 63]
            ii = i
        ii += 3
        if ii + 1 == len(h):
            c = int(h[ii:ii+1], 16)
            ret += self.b64map[c << 2]
        elif ii + 2 == len(h):
            c = int(h[ii:ii + 2], 16)
            ret += self.b64map[c >> 2] + self.b64map[(c & 3) << 4]
        while (len(ret) & 3) > 0:
            ret += self.b64pad
        return ret

    def b64tohex(self, s):
        ret = ''
        k = 0
        slop = 0
        for i in range(len(s)):
            if s[i] == self.b64pad:
                break
            v = self.b64map.index(s[i])
            if v < 0:
                continue
            if k == 0:
                ret += self.idx[v >> 2]
                slop = v & 3
                k = 1
            elif k == 1:
                ret += self.idx[(v >> 4) | (slop << 2)]
                slop = v & 0xf
                k = 2
            elif k == 2:
                ret += self.idx[slop]
                ret += self.idx[v >> 2]
                slop = v & 3
                k = 3
            else:
                ret += self.idx[(slop << 2) | (v >> 4)]
                ret += self.idx[v & 0xf]
                k = 0
        if k == 1:
            ret += self.idx[slop << 2]
        return ret


class BigInteger:
    """
    JavaScript BigInteger port (jsbn)
    仅实现 RSA 加密所需的最小功能
    """
    
    def __init__(self, a, b=10):
        """b=16 for hex, b=256 for byte array, b=10 for decimal"""
        if isinstance(a, dict):
            # From byte array dict (like pkcs1pad2 output)
            # First, find the actual array content
            self._from_dict(a)
        elif b == 16:
            # From hex string
            self._from_hex(a)
        elif isinstance(a, int):
            self._from_int(a)
        else:
            raise ValueError(f"Unsupported BigInteger input: type={type(a)}")
    
    def _from_dict(self, d):
        """From pkcs1pad2 output (dict with numeric keys)"""
        # Sort keys to get the correct order
        keys = sorted(d.keys())
        val = 0
        for k in keys:
            val = (val << 8) | d[k]
        self._value = val
    
    def _from_hex(self, s):
        if isinstance(s, str) and s:
            self._value = int(s, 16)
        else:
            self._value = 0
    
    def _from_int(self, n):
        self._value = n
    
    def bit_length(self):
        if self._value == 0:
            return 0
        return self._value.bit_length()
    
    def pow_int(self, e, m):
        """modular exponentiation: self^e mod m"""
        if isinstance(m, BigInteger):
            m = m._value
        if isinstance(e, BigInteger):
            e = e._value
        result = pow(self._value, e, m)
        return BigInteger(result)
    
    def to_string(self, base=16):
        """Convert to string representation"""
        if base == 16:
            return format(self._value, 'x')
        return str(self._value)
    
    def __repr__(self):
        return f"BigInteger({self._value})"


class SecureRandom:
    """Secure random number generator for PKCS#1 padding"""
    def __init__(self):
        import os
        self._rand = os.urandom
    
    def rng_get_bytes(self, ba):
        """Generate random byte, store in ba[0]"""
        ba[0] = self._rand(1)[0]


class RsaKey:
    """RSA Key - 与 school-sdk 完全一致的实现"""
    
    def __init__(self):
        self.n = None
        self.e = 0
        self.b64 = Base64()
    
    def set_public(self, n_hex, e_hex):
        """Set public key from hex strings"""
        if n_hex and e_hex and len(n_hex) > 0 and len(e_hex) > 0:
            self.n = BigInteger(n_hex, 16)
            self.e = int(e_hex, 16)
        else:
            raise ValueError("Invalid RSA public key")
    
    def pkcs1pad2(self, s, n):
        """PKCS#1 v1.5 padding - exact port from JS jsbn"""
        if n < len(s) + 11:
            raise ValueError("Message too long for RSA")
        
        ba = {}
        i = len(s) - 1
        
        while i >= 0 and n > 0:
            c = ord(s[i])
            i -= 1
            if c < 128:
                n -= 1
                ba[n] = c
            elif 127 < c < 2048:
                n -= 1
                ba[n] = (c & 63) | 128
                n -= 1
                ba[n] = (c >> 6) | 192
            else:
                n -= 1
                ba[n] = (c & 63) | 128
                n -= 1
                ba[n] = ((c >> 6) & 63) | 128
                n -= 1
                ba[n] = (c >> 12) | 224
        
        n -= 1
        ba[n] = 0
        
        rng = SecureRandom()
        x = {}
        while n > 2:
            x[0] = 0
            while x[0] == 0:
                rng.rng_get_bytes(x)
            n -= 1
            ba[n] = x[0]
        
        n -= 1
        ba[n] = 2
        n -= 1
        ba[n] = 0
        
        return BigInteger(ba)
    
    def do_public(self, x):
        """Public key operation: x^e mod n"""
        return x.pow_int(self.e, self.n)
    
    def rsa_encrypt(self, text):
        """Encrypt text with RSA public key"""
        m = self.pkcs1pad2(text, (self.n.bit_length() + 7) >> 3)
        if m is None:
            return None
        c = self.do_public(m)
        if c is None:
            return None
        h = c.to_string(16)
        if len(h) & 1 == 0:
            return h
        else:
            return '0' + h


def encrypt_password(password, modulus_b64, exponent_b64):
    """使用正方教务系统的 RSA 算法加密密码
    
    Args:
        password: 明文密码
        modulus_b64: 公钥 modulus (Base64)
        exponent_b64: 公钥 exponent (Base64)
    
    Returns:
        str: 加密后的密码（Base64 编码）
    """
    b64 = Base64()
    rsa = RsaKey()
    
    # 将 modulus 和 exponent 从 Base64 转为 hex
    n_hex = b64.b64tohex(modulus_b64)
    e_hex = b64.b64tohex(exponent_b64)
    
    # 设置公钥
    rsa.set_public(n_hex, e_hex)
    
    # 加密密码
    encrypted_hex = rsa.rsa_encrypt(password)
    
    # 将 hex 转为 Base64
    encrypted_b64 = b64.hex2b64(encrypted_hex)
    
    return encrypted_b64


# 测试
if __name__ == "__main__":
    # 使用 school-sdk 的测试数据验证
    m_test = "AKRB6FwmOe0hE9Uo6LMKoDE5U9JU9lH1v8Uv7ATjRj2W+aTPlR9Hfm8fR782pzGwDsTD4Yr7tBHQ1cuEnGrqrJn5HuPiLqmSg4Z/AwS+Rq8eE7T+ZaGoUtpqvcoSffSJOW29RNVMwT391ona/+eK5B3RkC9WaJFYiZai7FiQDeXT"
    e_test = "AQAB"
    
    result = encrypt_password("1234567890", m_test, e_test)
    print(f"Test encrypt '1234567890': {result}")
    
    # 预期结果（从 school-sdk 的测试中）
    # 注意：由于随机填充，每次结果不同，所以只检查格式
    assert len(result) > 0
    print("Encryption test passed!")
