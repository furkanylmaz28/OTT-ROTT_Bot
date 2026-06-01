//+------------------------------------------------------------------+
//|              DownloadAllHistoryGCM.mq4                           |
//|  GCM MT4'te Market Watch'taki TÜM sembollerin history'sini       |
//|  otomatik indirir.                                                |
//|                                                                   |
//|  KULLANIM:                                                        |
//|   1. Önce MT4'te Market Watch'a tüm sembolleri ekle:              |
//|      - Ctrl+M (Market Watch)                                      |
//|      - Sağ tık → "Show All" / "Tümünü Göster"                    |
//|   2. Bu script'i MQL4/Scripts klasörüne kopyala                  |
//|   3. MetaEditor'da F7 ile compile et                              |
//|   4. Bir grafiğin üzerine sürükle bırak                          |
//|   5. Bekle — 5-20 dakika sürer (sembol sayısına göre)            |
//|                                                                   |
//+------------------------------------------------------------------+
#property copyright "OTT Bot"
#property version   "1.00"
#property strict
#property show_inputs

// İndirilecek timeframe'ler (M5, M15, M30, H1, H4, D1)
extern bool Download_M5  = false;  // M5 dahil et (büyük dosya)
extern bool Download_M15 = false;
extern bool Download_M30 = true;   // Crypto için
extern bool Download_H1  = true;   // Hisse/Forex için
extern bool Download_H4  = true;
extern bool Download_D1  = true;
extern int  Bars_Per_Symbol = 5000;  // Sembol başına kaç bar

void OnStart()
{
   int total = SymbolsTotal(true);  // Sadece Market Watch'takiler
   Print("=== GCM HISTORY DOWNLOAD ===");
   Print("Market Watch'ta toplam ", total, " sembol var");
   Print("Tahmini süre: ", total/10, " - ", total/5, " dakika");
   Print("");

   int success = 0, failed = 0;
   int tf_list[6];
   int tf_count = 0;
   if(Download_M5)  { tf_list[tf_count++] = PERIOD_M5; }
   if(Download_M15) { tf_list[tf_count++] = PERIOD_M15; }
   if(Download_M30) { tf_list[tf_count++] = PERIOD_M30; }
   if(Download_H1)  { tf_list[tf_count++] = PERIOD_H1; }
   if(Download_H4)  { tf_list[tf_count++] = PERIOD_H4; }
   if(Download_D1)  { tf_list[tf_count++] = PERIOD_D1; }

   for(int i = 0; i < total; i++)
   {
      string sym = SymbolName(i, true);  // Market Watch sembolü
      Print("[", i+1, "/", total, "] ", sym, " ...");

      for(int t = 0; t < tf_count; t++)
      {
         int tf = tf_list[t];
         // iClose çağrısı history'yi tetikler
         double price = iClose(sym, tf, 0);
         int bars = iBars(sym, tf);

         // Eğer veri yoksa tekrar dene (3 saniye bekle)
         int retry = 0;
         while(bars < Bars_Per_Symbol && retry < 3)
         {
            Sleep(500);  // 500ms bekle
            price = iClose(sym, tf, Bars_Per_Symbol - 1);  // En geriden iste
            bars = iBars(sym, tf);
            retry++;
         }

         string tf_str = PeriodToStr(tf);
         if(bars > 100)
         {
            Print("    ", tf_str, ": ✓ ", bars, " bar");
            success++;
         }
         else
         {
            Print("    ", tf_str, ": ✗ veri alınamadı (", bars, " bar)");
            failed++;
         }
      }
      // Server'a yük bindirmemek için kısa bekleme
      Sleep(100);
   }

   Print("");
   Print("=== TAMAM ===");
   Print("Başarılı: ", success, " · Başarısız: ", failed);
   Print("Toplam sembol: ", total);
   Print("");
   Print("Şimdi PowerShell'de şunu çalıştır:");
   Print("  cd C:\\Users\\furka\\Desktop\\ott_bot");
   Print("  python extract_gcm_symbols.py");

   Alert("GCM history download tamamlandı! ", success, " başarılı, ", failed, " başarısız.");
}

string PeriodToStr(int p)
{
   switch(p)
   {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
   }
   return IntegerToString(p);
}
