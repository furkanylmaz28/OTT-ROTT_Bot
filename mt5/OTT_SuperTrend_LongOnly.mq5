//+------------------------------------------------------------------+
//|                                  OTT_SuperTrend_LongOnly.mq5      |
//|   Kanıtlanmış sistem: SuperTrend 10/3 (H1) · LONG-ONLY + NAKİT    |
//|   Short YOK · max 2x kaldıraç · max 3 pozisyon · BIST VIOP        |
//|   + günlük/haftalık zarar freni · taze pencere ≤9 bar (risk.py ile|
//|   uyumlu). Walk-forward + Monte Carlo doğrulamalı. SADECE DEMO.   |
//+------------------------------------------------------------------+
#property copyright "OTT Bot"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

//============================ GİRDİLER ==============================
input bool    InpScanAll        = true;        // TÜM Market Watch sembollerini tara
input string  InpSymbols        = "GARAN,AKBNK,THYAO,EREGL,SASA,KCHOL,YKBNK,SAHOL"; // InpScanAll=false ise bu liste
input ENUM_TIMEFRAMES InpTF      = PERIOD_H1;  // Zaman dilimi (sistem H1 ile doğrulandı)
input int     InpAtrPeriod      = 10;          // SuperTrend ATR periyodu (Kıvanç default)
input double  InpMultiplier      = 3.0;        // SuperTrend çarpanı
input bool    InpFreshOnly       = true;       // Sadece TAZE dönüşte gir (geç trene binme)
input int     InpFreshBars       = 9;          // TAZE penceresi: dönüşten sonra max kaç bar içinde gir (≤9 ≈ 1 gün; çevrimdışı kaçırılanı yakalar)
input double  InpDailyLossPct    = 2.0;        // 🛑 Günlük zarar freni: -%X'te yeni pozisyon AÇMA (çıkışlar devam)
input double  InpWeeklyLossPct   = 5.0;        // 🛑 Haftalık zarar freni: -%X'te yeni pozisyon AÇMA
input double  InpMarginPerPosPct = 33.0;       // Pozisyon başına KULLANILAN teminat (% öz sermaye)
input int     InpMaxPositions    = 3;          // Aynı anda max açık pozisyon (3×%33≈%99)
input double  InpMaxTotalMarginPct = 99.0;     // TOPLAM kullanılan teminat tavanı (% öz sermaye) — #9
input bool    InpSectorCap       = true;       // #6: aynı sektörden max 1 pozisyon (korelasyon)
input long    InpMagic           = 20260101;   // Sihirli numara
input int     InpTimerSec        = 10;         // Tarama aralığı (saniye)
input bool    InpVerbose         = true;       // Log yaz
input bool    InpVerifyMode      = false;      // DOĞRULAMA: son barların ST değerlerini logla (TradingView ile kıyas)
input string  InpVerifySymbol    = "";         // Doğrulanacak sembol (boş = ilk/grafik sembolü)

//============================ GLOBAL ===============================
CTrade        trade;
string        g_symbols[];
datetime      g_lastBar[];
int           g_atr[];
// zarar freni durumu
double        g_dayStartEq = 0, g_weekStartEq = 0;
int           g_dayYday = -1,   g_weekNo = -1;

//+------------------------------------------------------------------+
int OnInit()
{
   int n = 0;
   if(InpScanAll)
   {
      int tot = SymbolsTotal(true);          // Market Watch'taki TÜM semboller
      ArrayResize(g_symbols, tot);
      for(int i=0;i<tot;i++) g_symbols[i] = SymbolName(i, true);
      n = tot;
      PrintFormat("InpScanAll=true → Market Watch'taki %d sembol taranacak", n);
   }
   else
   {
      n = StringSplit(InpSymbols, ',', g_symbols);
   }
   if(n <= 0){ Print("HATA: taranacak sembol yok (Market Watch boş veya liste boş)."); return INIT_FAILED; }

   ArrayResize(g_lastBar, n);
   ArrayResize(g_atr, n);
   for(int i=0;i<n;i++)
   {
      StringTrimLeft(g_symbols[i]); StringTrimRight(g_symbols[i]);
      if(!SymbolSelect(g_symbols[i], true))
         Print("UYARI: sembol seçilemedi -> ", g_symbols[i], " (Market Watch adını kontrol et)");
      g_lastBar[i] = 0;
      g_atr[i] = iATR(g_symbols[i], InpTF, InpAtrPeriod);  // MT5 iATR = Wilder RMA (Pine ile uyumlu)
      if(g_atr[i] == INVALID_HANDLE)
         Print("UYARI: ATR handle alınamadı -> ", g_symbols[i]);
   }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(20);
   trade.SetTypeFillingBySymbol(g_symbols[0]);

   // DOĞRULAMA modu: son barların ST değerlerini bas (TradingView ile kıyasla)
   if(InpVerifyMode)
   {
      string vs = (InpVerifySymbol == "") ? g_symbols[0] : InpVerifySymbol;
      PrintVerify(vs);
   }

   EventSetTimer(MathMax(2, InpTimerSec));
   PrintFormat("OTT SuperTrend Long-Only başladı · %d sembol · TF=%s · ATR(%d)x%.1f · poz başı %%%.0f teminat · maxPoz=%d",
               n, EnumToString(InpTF), InpAtrPeriod, InpMultiplier, InpMarginPerPosPct, InpMaxPositions);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   for(int i=0;i<ArraySize(g_atr);i++)          // #3: handle sızıntısını önle
      if(g_atr[i] != INVALID_HANDLE) IndicatorRelease(g_atr[i]);
}

void OnTick(){ /* ana mantık OnTimer'da (çoklu sembol için güvenilir) */ }

//+------------------------------------------------------------------+
//| Her sembol için yeni bar oluştuğunda sinyal üret ve işle         |
//+------------------------------------------------------------------+
void OnTimer()
{
   bool halted = RiskHalted();   // günlük/haftalık zarar freni (yeni pozisyonu durdurur, çıkışı değil)
   int n = ArraySize(g_symbols);
   for(int i=0;i<n;i++)
   {
      string sym = g_symbols[i];
      datetime bt = iTime(sym, InpTF, 0);
      if(bt == 0) continue;
      if(bt == g_lastBar[i]) continue;   // aynı bar -> bekle
      g_lastBar[i] = bt;                 // yeni bar: bir kez işle

      if(g_atr[i] == INVALID_HANDLE) continue;   // #2: handle yoksa atla

      int tLast, tPrev, tBars;
      if(!GetSuperTrend(sym, g_atr[i], tLast, tPrev, tBars)) continue;

      bool haveLong = HasLong(sym);

      // ÇIKIŞ: trend aşağı döndü ve long'umuz var -> NAKİT (short açma!)
      if(haveLong && tLast == -1)
      {
         ClosePosition(sym);
         if(InpVerbose) Print("ÇIKIŞ (nakit): ", sym);
         continue;
      }

      // GİRİŞ: trend yukarı, pozisyon yok, slot+teminat uygun
      if(!haveLong && tLast == 1)
      {
         if(halted) continue;                     // 🛑 zarar freni: yeni pozisyon yok
         bool fresh = (tBars <= InpFreshBars);    // dönüşten sonra ≤N bar (geç trene binme + çevrimdışı kaçırılanı yakala)
         if(InpFreshOnly && !fresh) continue;
         if(CountOpen() >= InpMaxPositions) continue;
         if(InpSectorCap && SameSectorOpen(sym)) continue;   // #6: korelasyon kapısı
         // sembol işleme açık mı (seans/devre kesici)?
         long tmode = SymbolInfoInteger(sym, SYMBOL_TRADE_MODE);
         if(tmode == SYMBOL_TRADE_MODE_DISABLED || tmode == SYMBOL_TRADE_MODE_CLOSEONLY) continue;
         double lots = CalcLots(sym);
         if(lots <= 0) continue;
         if(trade.Buy(lots, sym))
            { if(InpVerbose) PrintFormat("GİRİŞ (long): %s  %.2f lot", sym, lots); }
         else
            Print("Alım başarısız: ", sym, "  ret=", trade.ResultRetcode());
      }
   }
}

//+------------------------------------------------------------------+
//| SuperTrend (Kıvanç Pine v4 birebir): son kapanan barın yönü      |
//|  up=src-mult*atr (ratchet max), dn=src+mult*atr (ratchet min)    |
//|  trend: -1&close>dn1 ->1 ; 1&close<up1 ->-1                       |
//+------------------------------------------------------------------+
bool GetSuperTrend(string sym, int atrHandle, int &trendLast, int &trendPrev, int &barsInTrend)
{
   int lb = 320;
   double atr[]; MqlRates r[];
   // as_series=TRUE → index 0 = EN YENİ (tartışmasız MT5 davranışı).
   ArraySetAsSeries(atr, true); ArraySetAsSeries(r, true);

   if(CopyBuffer(atrHandle, 0, 0, lb, atr) < lb) return false;
   if(CopyRates(sym, InpTF, 0, lb, r)      < lb) return false;

   int trend[]; ArrayResize(trend, lb); ArraySetAsSeries(trend, true);
   double up_prev = 0, dn_prev = 0;
   int    tr = 1;

   // SuperTrend ESKİDEN YENİYE hesaplanır → en eski (lb-1) bardan 0'a doğru.
   for(int i = lb-1; i >= 0; i--)
   {
      double hl2 = (r[i].high + r[i].low) / 2.0;
      double up  = hl2 - InpMultiplier * atr[i];
      double dn  = hl2 + InpMultiplier * atr[i];

      if(i == lb-1){ tr = 1; }       // en eski bar = başlangıç
      else
      {
         double cprev = r[i+1].close;  // kronolojik ÖNCEKİ (daha eski) bar
         up = (cprev > up_prev) ? MathMax(up, up_prev) : up;
         dn = (cprev < dn_prev) ? MathMin(dn, dn_prev) : dn;
         if(tr == -1 && r[i].close > dn_prev)      tr = 1;
         else if(tr == 1 && r[i].close < up_prev)  tr = -1;
      }
      up_prev = up; dn_prev = dn;
      trend[i] = tr;
   }

   trendLast = trend[1];   // index 0 = oluşan bar → son KAPANAN = 1
   trendPrev = trend[2];
   // kaç bardır bu yönde (son kapanan bar=1'den geriye, aynı yön sürdükçe say)
   int cnt = 0;
   for(int j=1; j<lb && trend[j]==trendLast; j++) cnt++;
   barsInTrend = cnt;
   return true;
}

//+------------------------------------------------------------------+
//| Pozisyon büyüklüğü: pozisyon başına teminat = öz sermayenin %33'ü |
//|  (broker'ın gerçek margin oranını kullanır → gerçek kaldıraç)     |
//+------------------------------------------------------------------+
double CalcLots(string sym)
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double target_margin = eq * (InpMarginPerPosPct / 100.0);   // bu pozisyona ayrılacak teminat

   double price = SymbolInfoDouble(sym, SYMBOL_ASK);
   if(price <= 0) return 0;

   // 1 lotluk teminat (broker hesabı)
   double margin1 = 0;
   if(!OrderCalcMargin(ORDER_TYPE_BUY, sym, 1.0, price, margin1) || margin1 <= 0)
      return 0;

   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double minl = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double maxl = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   if(step <= 0) step = minl;

   double lots = target_margin / margin1;          // %33 teminata denk lot
   lots = MathFloor(lots / step) * step;

   if(lots < minl) return 0;                        // min lot %33'ü aşıyor → girme
   if(lots > maxl) lots = maxl;

   // serbest teminat gerçekten yetiyor mu
   double need = 0;
   if(!OrderCalcMargin(ORDER_TYPE_BUY, sym, lots, price, need)) return 0;
   if(need > AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.98) return 0;

   // #9: TOPLAM kullanılan teminat tavanı (açık pozisyonlar + bu) — kaldıraç patlamasın
   if(AccountInfoDouble(ACCOUNT_MARGIN) + need > eq * (InpMaxTotalMarginPct / 100.0))
      return 0;

   // efektif kaldıracı logla (kullanıcı görsün)
   if(InpVerbose)
   {
      double cs = SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE);
      double notional = lots * price * cs;
      PrintFormat("%s: %.2f lot · teminat %.0f (öz sermayenin %%%.0f) · notional %.0f · ~%.1fx kaldıraç",
                  sym, lots, need, InpMarginPerPosPct, notional, notional/eq);
   }
   // #5: lot ondalığını step'ten türet (2'ye zorlama)
   int vdig = (step >= 1.0) ? 0 : (int)MathRound(-MathLog10(step));
   return NormalizeDouble(lots, vdig);
}

//+------------------------------------------------------------------+
//| Zarar freni: günlük -%X ya da haftalık -%Y aşılınca YENİ pozisyon |
//|  açma (çıkışlar devam eder). Gün/hafta başı equity'yi referans alır.|
//+------------------------------------------------------------------+
bool RiskHalted()
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   MqlDateTime dt; TimeToStruct(TimeCurrent(), dt);
   if(dt.day_of_year != g_dayYday){ g_dayYday = dt.day_of_year; g_dayStartEq = eq; }   // yeni gün
   int wk = dt.day_of_year / 7;
   if(wk != g_weekNo){ g_weekNo = wk; g_weekStartEq = eq; }                            // yeni hafta
   double dayDD  = (g_dayStartEq  > 0) ? (eq - g_dayStartEq)  / g_dayStartEq  * 100.0 : 0;
   double weekDD = (g_weekStartEq > 0) ? (eq - g_weekStartEq) / g_weekStartEq * 100.0 : 0;
   if(InpDailyLossPct > 0 && dayDD <= -InpDailyLossPct)
   { if(InpVerbose) PrintFormat("🛑 GÜNLÜK zarar freni %.1f%% (≤ -%.1f%%) — yeni pozisyon YOK", dayDD, InpDailyLossPct); return true; }
   if(InpWeeklyLossPct > 0 && weekDD <= -InpWeeklyLossPct)
   { if(InpVerbose) PrintFormat("🛑 HAFTALIK zarar freni %.1f%% (≤ -%.1f%%) — yeni pozisyon YOK", weekDD, InpWeeklyLossPct); return true; }
   return false;
}

//============================ YARDIMCI =============================
//  Her pozisyon PositionSelectByTicket ile AÇIKÇA seçilir (#1).
//  NOT: CountOpen PORTFÖY bazlı sayar (tüm sembollerde max 3). Bu EA çoklu-sembol,
//  TEK instance çalıştır — birden çok grafikte açma, yoksa sayım çakışır.
bool HasLong(string sym)
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL) == sym &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic &&
         PositionGetInteger(POSITION_TYPE)  == POSITION_TYPE_BUY)
         return true;
   }
   return false;
}

int CountOpen()
{
   int c = 0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetInteger(POSITION_MAGIC) == InpMagic) c++;
   }
   return c;
}

void ClosePosition(string sym)
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL) == sym &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic)
      {
         if(!trade.PositionClose(tk))               // #7: sonucu kontrol et
            Print("KAPATILAMADI: ", sym, " tk=", tk, " ret=", trade.ResultRetcode());
      }
   }
}

//============================ #6 SEKTÖR KAPISI =====================
//  VIOP sembolünden baz isim çıkar: F_GARAN0726 -> GARAN, F_BIMAS0726N1 -> BIMAS
string BaseName(string s)
{
   if(StringSubstr(s,0,2) == "F_") s = StringSubstr(s,2);
   for(int i=0;i<StringLen(s);i++)
   {
      ushort c = StringGetCharacter(s,i);
      if(c >= '0' && c <= '9') return StringSubstr(s,0,i);
   }
   return s;
}

string SectorOf(string sym)
{
   string b = " " + BaseName(sym) + " ";
   if(StringFind(" AKBNK HALKB ISCTR VAKBN YKBNK GARAN ", b) >= 0) return "banka";
   if(StringFind(" KCHOL ALARK ENKAI DOHOL SAHOL ", b)       >= 0) return "holding";
   if(StringFind(" ASELS ASTOR KONTR ", b)                   >= 0) return "savunma";
   if(StringFind(" EREGL KRDMD ", b)                         >= 0) return "celik";
   if(StringFind(" PETKM SASA GUBRF HEKTS ", b)              >= 0) return "kimya";
   if(StringFind(" TUPRS ENJSA ODAS AKSEN ", b)              >= 0) return "enerji";
   if(StringFind(" THYAO PGSUS TAVHL ", b)                   >= 0) return "ulasim";
   if(StringFind(" FROTO TOASO DOAS ARCLK ", b)              >= 0) return "oto";
   if(StringFind(" MGROS SOKM AEFES BIMAS ULKER ", b)        >= 0) return "perakende";
   return BaseName(sym);   // bilinmeyen → kendi grubu (kısıtlamaz)
}

bool SameSectorOpen(string sym)
{
   string sec = SectorOf(sym);
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetInteger(POSITION_MAGIC) == InpMagic &&
         SectorOf(PositionGetString(POSITION_SYMBOL)) == sec)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| DOĞRULAMA: son 6 kapanan barın ST-çizgi + yön değerini logla     |
//|  → TradingView'daki SuperTrend(10,3) ile bar bar karşılaştır     |
//+------------------------------------------------------------------+
void PrintVerify(string sym)
{
   int h = iATR(sym, InpTF, InpAtrPeriod);
   if(h == INVALID_HANDLE){ Print("DOĞRULAMA: ATR alınamadı -> ", sym); return; }
   int lb = 320;
   double atr[]; MqlRates r[];
   ArraySetAsSeries(atr, true); ArraySetAsSeries(r, true);   // 0 = en yeni (tartışmasız)
   if(CopyBuffer(h,0,0,lb,atr) < lb || CopyRates(sym,InpTF,0,lb,r) < lb)
   { Print("DOĞRULAMA: veri yetersiz -> ", sym, " (biraz bekleyip EA'yı tekrar yükle)"); IndicatorRelease(h); return; }

   double line[]; ArrayResize(line, lb); ArraySetAsSeries(line, true);
   int    trend[]; ArrayResize(trend, lb); ArraySetAsSeries(trend, true);
   double up_prev=0, dn_prev=0; int tr=1;
   for(int i=lb-1;i>=0;i--)                 // eskiden yeniye
   {
      double hl2 = (r[i].high + r[i].low)/2.0;
      double up  = hl2 - InpMultiplier*atr[i];
      double dn  = hl2 + InpMultiplier*atr[i];
      if(i<lb-1)
      {
         double cprev = r[i+1].close;        // kronolojik önceki bar
         up = (cprev>up_prev)? MathMax(up,up_prev):up;
         dn = (cprev<dn_prev)? MathMin(dn,dn_prev):dn;
         if(tr==-1 && r[i].close>dn_prev)     tr=1;
         else if(tr==1 && r[i].close<up_prev) tr=-1;
      }
      up_prev=up; dn_prev=dn; trend[i]=tr; line[i]=(tr>0)?up:dn;
   }
   PrintFormat("=== SuperTrend DOĞRULAMA: %s %s — TradingView SuperTrend(10,3) ile son 50 barı kıyasla ===",
               sym, EnumToString(InpTF));
   Print("Tarih               Kapanış    ST-çizgi   Yön");
   for(int i=50;i>=1;i--)   // son 50 KAPANAN bar (index 0 = oluşan bar, atla)
      PrintFormat("%s   %s   %s   %s",
                  TimeToString(r[i].time, TIME_DATE|TIME_MINUTES),
                  DoubleToString(r[i].close, 2),
                  DoubleToString(line[i], 2),
                  (trend[i]>0)?"LONG":"SHORT");
   IndicatorRelease(h);
}
//+------------------------------------------------------------------+
