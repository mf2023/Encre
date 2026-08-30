# Veri İşleme Özeti —— Türkiye

**Son Güncelleme：22 Ağustos 2026**

**Uygulama Kapsamı:** Bu özet, Dunimd'in Türkiye'deki hizmetlerindeki veri işlemini açıklar. Türkiye'deki kullanıcılar için tek bağlayıcı sürümdür.

> İlgili belgeler: [Gizlilik Politikası](PRIVACY.md) · [Hizmet Şartları](TERMS.md) · [Kullanıcı Sözleşmesi](USER_AGREEMENT.md) · [Çocukların Gizliliği](MINORS_PRIVACY.md) · [İçerik Kuralları](CONTENT_GUIDELINES.md)

## İçindekiler

1. [Yerel öncelik beyanı](#1-yerel-öncelik-beyanı)
2. [Veri akışları](#2-veri-akışları)
3. [Hizmet bazında işleme](#3-hizmet-bazında-işleme)
4. [Telemetri](#4-telemetri)
5. [Yurt dışına aktarım](#5-yurt-dışına-aktarım)
6. [Güvenlik ve ihlal bildirimi](#6-güvenlik-ve-ihlal-bildirimi)
7. [Değişiklikler ve iletişim](#7-değişiklikler-ve-iletişim)

---

## 1. Yerel öncelik beyanı

1.1 Encre Agent yerelde çalışacak şekilde tasarlanmıştır: Ajan tanımları, komut istemleri, yanıtlar ve geçmiş cihazınızda kalır.

1.2 Telemetri varsayılan olarak kapalıdır; komut istemleri ve yanıtlar varsayılan saklanmaz.

1.3 Cihaz dışı işleme yalnızca isteğe bağlı bulut hizmetleriyle gerçekleşir.

## 2. Veri akışları

| Veri | Konum | Süre |
|---|---|---|
| Ajan yapılandırmaları, akışlar | Yalnızca cihaz | Silinene kadar |
| Konuşma geçmişi | Yalnızca cihaz | Kullanıcı kontrolünde |
| API anahtarları (3. taraf sağlayıcı) | Cihazda şifreli | Silinene kadar |
| Bulut çıkarım talepleri | İşlem sonrası silme | Oturum süresi |
| Hizmet meta verisi (zaman damgası, hata kodu) | Sunucu | En fazla 30 gün |
| Telemetri (tercihe bağlı) | Sunucu | En fazla 90 gün |
| Hesap verileri (yalnızca bulut) | Sunucu | Hesap silinene kadar |

## 3. Hizmet bazında işleme

3.1 **PiscesLx:** Talepler TLS ile taşınır, bellekte işlenir; meta veri en fazla 30 gün tutulup otomatik silinir.

3.2 **Encre Agent Masaüstü/Framework:** Sunucu tarafı işlem yoktur.

3.3 **Dunimd Enterprise:** İşlem, veri sorumlusu adına veri işleyici sözleşmesi çerçevesinde yürütülür.

## 4. Telemetri

4.1 Telemetri kesinlikle katılım esaslıdır (opt-in): açık onayınız olmadan tanılama verisi gönderilmez.

4.2 Ayarlardan her an kapatılabilir; kapatıldığında yeni toplama durur, mevcut veriler silinir.

## 5. Yurt dışına aktarım

5.1 İşleme ağırlıklı olarak Türkiye'deki kullanıcı cihazlarında kalır.

5.2 Gerekli hallerde yurt dışı aktarımı KVKK md. 9'a uygun yapılır: Kurul'un yayımladığı **Standart Sözleşme'nin imzalanması ve Kurul'a bildirilmesi** (Kurul Kararı 2024/959) temel yöntemimizdir; ayrıca Kurul onaylı Bağlayıcı Şirket Kuralları veya kanundaki arızi haller uygulanabilir.

5.3 Halihazırda Kurul tarafından yeterlilik kararı ilan edilen ülke bulunmamaktadır.

## 6. Güvenlik ve ihlal bildirimi

6.1 Teknik önlemler: TLS 1.2+ taşıma şifrelemesi, AES-256-GCM bekleyen veri şifrelemesi.

6.2 Organizasyonel önlemler: gizlilik taahhüdü, erişim kayıtları, olay müdahale planı ([SECURITY.md](../../../SECURITY.md)).

6.3 **İhlal bildirimi:** Bir güvenlik ihlali halinde Kurul'a **en kısa sürede — Kurul Kararı 2019/10 gereği 72 saat içinde** bildirim yapılır; etkilenen kişiler gerekli duyurularla bilgilendirilir. Türkiye'deki kişileri etkileyen ihlallerde yurt dışında yerleşik veri sorumlusu olarak bu yükümlülüğü doğrudan yerine getiririz.

## 7. Değişiklikler ve iletişim

7.1 Bu özetin değişiklikleri en az **30 gün önce** duyurulur.

7.2 İletişim: dunimd@outlook.com · dunimd.com · Denetleyici makam: Kişisel Verileri Koruma Kurumu (kvkk.gov.tr)

---

*Bu metin bilgilendirme amaçlıdır ve hukuki tavsiye teşkil etmez.*
