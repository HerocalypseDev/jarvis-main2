package com.jarvis.locator;

import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * AES-256-GCM, the same format as jarvis_phone_locate.py: base64url(nonce[12] + ciphertext + tag[16]),
 * with "jloc1|<topic>" as associated data. The relay server only ever sees this text, never a position.
 */
final class Crypto {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int FLAGS = Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING;

    static String seal(Config cfg, String plain) throws Exception {
        byte[] nonce = new byte[12];
        RNG.nextBytes(nonce);
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(cfg.key, "AES"), new GCMParameterSpec(128, nonce));
        c.updateAAD(aad(cfg));
        byte[] ct = c.doFinal(plain.getBytes(StandardCharsets.UTF_8));
        byte[] out = new byte[nonce.length + ct.length];
        System.arraycopy(nonce, 0, out, 0, nonce.length);
        System.arraycopy(ct, 0, out, nonce.length, ct.length);
        return Base64.encodeToString(out, FLAGS);
    }

    /** Returns null for anything that wasn't sealed with this phone's key (or was changed on the way). */
    static String open(Config cfg, String text) {
        try {
            byte[] raw = Base64.decode(text.trim(), FLAGS);
            if (raw.length < 12 + 16) return null;
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(cfg.key, "AES"), new GCMParameterSpec(128, raw, 0, 12));
            c.updateAAD(aad(cfg));
            return new String(c.doFinal(raw, 12, raw.length - 12), StandardCharsets.UTF_8);
        } catch (Exception e) {
            return null;
        }
    }

    private static byte[] aad(Config cfg) {
        return ("jloc1|" + cfg.topic).getBytes(StandardCharsets.UTF_8);
    }
}
