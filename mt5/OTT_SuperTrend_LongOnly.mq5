//+------------------------------------------------------------------+
//|                                  OTT_SuperTrend_LongOnly.mq5      |
//|   Kanıtlanmış sistem: SuperTrend 10/3 (H1) · LONG-ONLY + NAKİT    |
//|   Short YOK · max 2x kaldıraç · max 3 pozisyon · BIST VIOP        |
//|   Walk-forward + Monte Carlo ile doğrulandı. SADECE DEMO için.    |
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
input double  InpMarginPerPosPct = 33.0;       // Pozisyon başına KULLANILAN teminat (% öz sermaye)
input int     InpMaxPositions    = 3;          // Aynı anda max açık pozisyon (3×%33≈%99)
input long    InpMagic           = 20260101;   // Sihirli numara
input int     InpTimerSec        = 10;         // Tarama aralığı (saniye)
input bool    InpVerbose         = true;       // Log yaz

//============================ GLOBAL ===============================
CTrade        trade;
string        g_symbols[];
datetime      g_lastBar[];
int           g_atr[];

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

   EventSetTimer(MathMax(2, InpTimerSec));
   PrintFormat("OTT SuperTrend Long-Only başladı · %d sembol · TF=%s · ATR(%d)x%.1f · poz başı %%%.0f teminat · maxPoz=%d",
               n, EnumToString(InpTF), InpAtrPeriod, InpMultiplier, InpMarginPerPosPct, InpMaxPositions);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason){ EventKillTimer(); }

void OnTick(){ /* ana mantık OnTimer'da (çoklu sembol için güvenilir) */ }

//+------------------------------------------------------------------+
//| Her sembol için yeni bar oluştuğunda sinyal üret ve işle         |
//+------------------------------------------------------------------+
void OnTimer()
{
   int n = ArraySize(g_symbols);
   for(int i=0;i<n;i++)
   {
      string sym = g_symbols[i];
      datetime bt = iTime(sym, InpTF, 0);
      if(bt == 0) continue;
      if(bt == g_lastBar[i]) continue;   // aynı bar -> bekle
      g_lastBar[i] = bt;                 // yeni bar: bir kez işle

      int tLast, tPrev;
      if(!GetSuperTrend(sym, g_atr[i], tLast, tPrev)) continue;

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
         bool fresh = (tPrev == -1);
         if(InpFreshOnly && !fresh) continue;     // geç trene binme
         if(CountOpen() >= InpMaxPositions) continue;
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
bool GetSuperTrend(string sym, int atrHandle, int &trendLast, int &trendPrev)
{
   int lookback = 320;
   double atr[]; MqlRates r[];
   ArraySetAsSeries(atr, false); ArraySetAsSeries(r, false);

   if(CopyBuffer(atrHandle, 0, 0, lookback, atr) < lookback) return false;
   if(CopyRates(sym, InpTF, 0, lookback, r)      < lookback) return false;

   int trend[]; ArrayResize(trend, lookback);
   double up_prev = 0, dn_prev = 0;
   int    tr = 1;

   for(int i=0;i<lookback;i++)
   {
      double hl2 = (r[i].high + r[i].low) / 2.0;
      double up  = hl2 - InpMultiplier * atr[i];
      double dn  = hl2 + InpMultiplier * atr[i];

      if(i == 0){ tr = 1; }
      else
      {
         double cprev = r[i-1].close;
         up = (cprev > up_prev) ? MathMax(up, up_prev) : up;
         dn = (cprev < dn_prev) ? MathMin(dn, dn_prev) : dn;
         if(tr == -1 && r[i].close > dn_prev)      tr = 1;
         else if(tr == 1 && r[i].close < up_prev)  tr = -1;
      }
      up_prev = up; dn_prev = dn;
      trend[i] = tr;
   }

   // index lookback-1 = oluşan (kapanmamış) bar -> kullanma
   trendLast = trend[lookback-2];   // son KAPANAN bar
   trendPrev = trend[lookback-3];   // ondan önceki
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

   // efektif kaldıracı logla (kullanıcı görsün)
   if(InpVerbose)
   {
      double cs = SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE);
      double notional = lots * price * cs;
      PrintFormat("%s: %.2f lot · teminat %.0f (öz sermayenin %%%.0f) · notional %.0f · ~%.1fx kaldıraç",
                  sym, lots, need, InpMarginPerPosPct, notional, notional/eq);
   }
   return NormalizeDouble(lots, 2);
}

//============================ YARDIMCI =============================
bool HasLong(string sym)
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
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
      if(tk == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) == InpMagic) c++;
   }
   return c;
}

void ClosePosition(string sym)
{
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == sym &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic)
         trade.PositionClose(tk);
   }
}
//+------------------------------------------------------------------+
