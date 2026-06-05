<?php
// Canonical phpass (the exact class WordPress bundles as class-phpass.php),
// trimmed to the portable-hash path. We use it to CheckPassword() a hash that
// our Python minted — if it returns true, our Python is byte-for-byte
// WordPress-compatible.
class PasswordHash {
    var $itoa64 = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
    function crypt_private($password, $setting) {
        $output = '*0';
        $count_log2 = strpos($this->itoa64, $setting[3]);
        if ($count_log2 < 7 || $count_log2 > 30) return $output;
        $count = 1 << $count_log2;
        $salt = substr($setting, 4, 8);
        if (strlen($salt) != 8) return $output;
        $hash = md5($salt . $password, TRUE);
        do { $hash = md5($hash . $password, TRUE); } while (--$count);
        $output = substr($setting, 0, 12);
        $output .= $this->encode64($hash, 16);
        return $output;
    }
    function encode64($input, $count) {
        $output = ''; $i = 0;
        do {
            $value = ord($input[$i++]);
            $output .= $this->itoa64[$value & 0x3f];
            if ($i < $count) $value |= ord($input[$i]) << 8;
            $output .= $this->itoa64[($value >> 6) & 0x3f];
            if ($i++ >= $count) break;
            if ($i < $count) $value |= ord($input[$i]) << 16;
            $output .= $this->itoa64[($value >> 12) & 0x3f];
            if ($i++ >= $count) break;
            $output .= $this->itoa64[($value >> 18) & 0x3f];
        } while ($i < $count);
        return $output;
    }
    function CheckPassword($password, $stored) {
        return $this->crypt_private($password, $stored) === $stored;
    }
}
$h = new PasswordHash();
$password = $argv[1];
$stored   = $argv[2];
echo $h->CheckPassword($password, $stored) ? "PHP says: VALID\n" : "PHP says: INVALID\n";
