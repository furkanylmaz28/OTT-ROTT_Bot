//+------------------------------------------------------------------+
//|                                              OTT_GOLD_EA.mq4     |
//|     Anıl Özekşi OTT-ailesi (TOTT + SOTT + HOTT/LOTT + ROTT)      |
//|     GOLD için optimize edilmiş — Python backtest'inden           |
//|                                                                   |
//|   GOLD M15 (DEFAULT — 29 ay backtest: +117.78% PF 4.41 DD -9.01%):|
//|     TrendLength=20  TrendPercent=8.0   MinorPercent=4.0          |
//|     TottPercent=1.0  TottCoeff=0.0004                            |
//|     SottPeriodK=500  SottSmoothK=200  SottPercent=0.2            |
//|     GateLength=28   GatePercent=0.4   gate_shift=2               |
//|                                                                   |
//|   GOLD M5  (11 ay backtest: +46.53% PF 3.04 DD -9.44%):           |
//|     TrendLength=40  TrendPercent=8.0   MinorPercent=4.0          |
//|     TottPercent=1.0  TottCoeff=0.0004                            |
//|     SottPeriodK=300  SottSmoothK=200  SottPercent=0.2            |
//|     GateLength=10   GatePercent=0.4   gate_shift=0               |
//|                                                                   |
//|   ÖNEMLİ — sistem FOREX paritelerinde ÇALIŞMIYOR. Sadece GOLD.    |
//+------------------------------------------------------------------+
#property copyright "OTT Family Bot — based on Anıl Özekşi"
#property version   "1.00"
#property strict

//── Strateji parametreleri (GOLD M15 optimum, sequential_optimize sonucu)
extern int    TrendLength       = 20;        // opt1
extern double TrendPercent      = 8.0;       // opt2 (major trend, 7 default)
extern double MinorPercent      = 4.0;       // opt3 (minor trend, 3.5 default)
extern double TottPercent       = 1.0;       // bölge OTT %
extern double TottCoeff         = 0.0004;    // TOTT band coefficient
extern int    SottPeriodK       = 500;       // SOTT stoch K period
extern int    SottSmoothK       = 200;       // SOTT smoothing
extern double SottPercent       = 0.2;       // SOTT OTT %
extern int    GateLength        = 28;        // HOTT/LOTT N
extern double GatePercent       = 0.4;       // HOTT/LOTT OTT %
extern int    RottX1            = 30;        // ROTT OTT length
extern int    RottX2            = 1000;      // ROTT VAR length
extern double RottPercent       = 7.0;       // ROTT OTT %

//── Trade parametreleri
extern double LotSize           = 0.10;
extern int    MagicNumber       = 770042;
extern int    Slippage          = 30;
extern bool   AllowLong         = true;
extern bool   AllowShort        = true;
extern bool   UseTimeFilter     = false;     // GOLD 24-saat
extern int    StartHour         = 0;
extern int    EndHour           = 24;

//── Risk yönetimi (canlı kullanım için kritik)
extern double DailyLossLimitPct = 3.0;        // %3 günlük kayıpta o gün trade etmez
extern double MaxDrawdownPct    = 15.0;       // Peak'ten %15 düşerse tüm pozisyonları kapat + EA durur
extern bool   UseRiskMgmt       = true;       // Risk yönetimi aktif mi?

double  g_peakEquity   = 0;
datetime g_dayStart    = 0;
double  g_dayStartEquity = 0;
bool    g_disabled     = false;

//── İç buffer'lar
double VAR_trend[], OTT_trend[];
double VAR_zone[],  OTT_zone[], OTTup_zone[], OTTdn_zone[];
double SOTT_k[],    SOTT_ott[];
double ROTT_ma[],   ROTT_ott[];
double HOTT_line[], LOTT_line[];

int    barsCount   = 0;
datetime lastBarTime = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   Print("OTT GOLD EA başladı. Symbol=", Symbol(), " TF=", PeriodAsString());
   g_peakEquity = AccountEquity();
   g_dayStart = StartOfDay(TimeCurrent());
   g_dayStartEquity = AccountEquity();
   return INIT_SUCCEEDED;
}

datetime StartOfDay(datetime t)
{
   return t - (t % 86400);
}

bool CheckRiskLimits()
{
   if(!UseRiskMgmt) return true;

   double eq = AccountEquity();

   // Günlük loss limit
   datetime today = StartOfDay(TimeCurrent());
   if(today != g_dayStart) {
      // Yeni gün başladı
      g_dayStart = today;
      g_dayStartEquity = eq;
   }
   double dayLossPct = (g_dayStartEquity - eq) / g_dayStartEquity * 100;
   if(dayLossPct >= DailyLossLimitPct) {
      Print("DAILY LOSS LIMIT (",DailyLossLimitPct,"%) aşıldı: ", dayLossPct, "% — bugün trade durduruldu");
      return false;
   }

   // Max drawdown
   if(eq > g_peakEquity) g_peakEquity = eq;
   double ddPct = (g_peakEquity - eq) / g_peakEquity * 100;
   if(ddPct >= MaxDrawdownPct) {
      Print("MAX DRAWDOWN (",MaxDrawdownPct,"%) aşıldı: ", ddPct, "% — TÜM POZİSYONLAR KAPATILDI, EA DURDU");
      CloseAllByType(OP_BUY);
      CloseAllByType(OP_SELL);
      g_disabled = true;
      return false;
   }

   return !g_disabled;
}

string PeriodAsString()
{
   switch(Period()) {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
   }
   return IntegerToString(Period());
}

//+------------------------------------------------------------------+
//| VAR (VIDYA) hesabı — Anıl Özekşi formülü                          |
//+------------------------------------------------------------------+
//  data[]: input series (e.g. Close)
//  length: VAR length
//  out[]:  result (must be sized properly)
//
//  Formula:
//    a = 9 (CMO penceresi)
//    alpha = 2/(length+1)
//    b[i] = max(data[i]-data[i-1], 0)
//    c[i] = max(data[i-1]-data[i], 0)
//    d = sum(b, 9)
//    e = sum(c, 9)
//    g = |(d-e)/(d+e)|
//    vidya[i] = g*alpha*(data[i]-vidya[i-1]) + vidya[i-1]
//
void ComputeVAR(const double &data[], int total, int length, double &out[])
{
   ArrayResize(out, total);
   ArrayInitialize(out, EMPTY_VALUE);
   if(length == 1) { for(int i=0;i<total;i++) out[i]=data[i]; return; }

   double alpha = 2.0/(length+1);
   bool started = false;
   double prev = 0;

   for(int i=0; i<total; i++)
   {
      // CMO 9-bar pencere
      double sumU=0, sumD=0;
      if(i < 8) { /* yetersiz veri */ }
      else {
         for(int j=0; j<9; j++) {
            int k = i - j;
            double diff = (k >= 1) ? data[k]-data[k-1] : 0.0;
            if(diff > 0) sumU += diff;
            else if(diff < 0) sumD += -diff;
         }
      }
      double g = 0;
      if(sumU + sumD > 0) g = MathAbs((sumU - sumD)/(sumU + sumD));

      // İlk SMA — length-1. barda gelir
      if(!started) {
         if(i >= length - 1) {
            double sma = 0;
            for(int m=0;m<length;m++) sma += data[i-m];
            sma /= length;
            prev = sma;
            out[i] = prev;
            started = true;
         }
         continue;
      }
      double cur = g * alpha * (data[i] - prev) + prev;
      out[i] = cur;
      prev = cur;
   }
}

//+------------------------------------------------------------------+
//| OTT hesabı — Anıl Özekşi formülü                                  |
//+------------------------------------------------------------------+
void ComputeOTT(const double &mavg[], int total, double percent,
                double &ott_out[])
{
   ArrayResize(ott_out, total);
   ArrayInitialize(ott_out, EMPTY_VALUE);
   double longStop[], shortStop[];
   int    dir[];
   ArrayResize(longStop, total);
   ArrayResize(shortStop, total);
   ArrayResize(dir, total);
   for(int i=0;i<total;i++) { longStop[i]=EMPTY_VALUE; shortStop[i]=EMPTY_VALUE; dir[i]=1; }

   for(int i=0; i<total; i++)
   {
      if(mavg[i] == EMPTY_VALUE) continue;
      double fark = mavg[i] * percent * 0.01;
      double ls = mavg[i] - fark;
      double ss = mavg[i] + fark;
      double ls_prev = (i==0 || longStop[i-1]==EMPTY_VALUE) ? ls : longStop[i-1];
      double ss_prev = (i==0 || shortStop[i-1]==EMPTY_VALUE) ? ss : shortStop[i-1];
      if(mavg[i] > ls_prev) ls = MathMax(ls, ls_prev);
      if(mavg[i] < ss_prev) ss = MathMin(ss, ss_prev);
      int d_prev = (i>0) ? dir[i-1] : 1;
      int d = d_prev;
      if(d_prev == -1 && mavg[i] > ss_prev) d = 1;
      else if(d_prev == 1 && mavg[i] < ls_prev) d = -1;
      double mt = (d == 1) ? ls : ss;
      double ott_val;
      if(mavg[i] > mt) ott_val = mt * (200 + percent) / 200;
      else             ott_val = mt * (200 - percent) / 200;
      longStop[i] = ls;
      shortStop[i] = ss;
      dir[i] = d;
      ott_out[i] = ott_val;
   }
}

//+------------------------------------------------------------------+
//| HOTT/LOTT hesabı                                                  |
//+------------------------------------------------------------------+
void ComputeHOTT(const double &high[], int total, int n, double percent, double &out[])
{
   double hhv_half[]; ArrayResize(hhv_half, total);
   int half = MathMax(n/2, 1);
   for(int i=0; i<total; i++) {
      double m = high[i];
      int start = MathMax(0, i - half + 1);
      for(int j=start; j<=i; j++) if(high[j] > m) m = high[j];
      hhv_half[i] = m;
   }
   ComputeOTT(hhv_half, total, percent, out);
}

void ComputeLOTT(const double &low[], int total, int n, double percent, double &out[])
{
   double llv_half[]; ArrayResize(llv_half, total);
   int half = MathMax(n/2, 1);
   for(int i=0; i<total; i++) {
      double m = low[i];
      int start = MathMax(0, i - half + 1);
      for(int j=start; j<=i; j++) if(low[j] < m) m = low[j];
      llv_half[i] = m;
   }
   ComputeOTT(llv_half, total, percent, out);
}

//+------------------------------------------------------------------+
//| Stochastic K (raw)                                                |
//+------------------------------------------------------------------+
void ComputeStoch(const double &close[], const double &high[], const double &low[],
                  int total, int period_k, double &out[])
{
   ArrayResize(out, total);
   ArrayInitialize(out, EMPTY_VALUE);
   for(int i=0; i<total; i++) {
      if(i < period_k - 1) continue;
      double hh = high[i], ll = low[i];
      for(int j=1; j<period_k; j++) {
         if(high[i-j] > hh) hh = high[i-j];
         if(low[i-j]  < ll) ll = low[i-j];
      }
      double rng = hh - ll;
      if(rng > 0) out[i] = 100.0 * (close[i] - ll) / rng;
      else out[i] = EMPTY_VALUE;
   }
}

//+------------------------------------------------------------------+
//| Ana sinyal hesabı                                                 |
//+------------------------------------------------------------------+
//  shift_eval=2 → bar shift_eval'in sinyalini değerlendir (kapanmış bar)
//  Geriye dönen:
//     buyLong, exitLong, buyShort, exitShort  (bool)
//
bool ComputeSignals(int shift_eval, bool &buyLong, bool &exitLong,
                    bool &buyShort, bool &exitShort)
{
   buyLong = exitLong = buyShort = exitShort = false;
   int total = MathMin(Bars, RottX2 + 200); // yeterli warmup
   if(total < RottX2 + 50) return false;

   // OHLC array'leri — pozisyon 0 son bar (en yeni)
   double op[], hi[], lo[], cl[];
   ArrayResize(op, total); ArrayResize(hi, total);
   ArrayResize(lo, total); ArrayResize(cl, total);

   // MT4'te i=0 son bar — biz array'i kronolojik (eski→yeni) sıralıyoruz
   // out[i] = en eski → en yeni. shift_eval = bar gerisi (sondan).
   for(int i=0; i<total; i++) {
      int src_shift = total - 1 - i;
      op[i] = Open[src_shift];
      hi[i] = High[src_shift];
      lo[i] = Low[src_shift];
      cl[i] = Close[src_shift];
   }

   // ── Trend katmanı
   ComputeVAR(cl, total, TrendLength, VAR_trend);
   ComputeOTT(VAR_trend, total, TrendPercent, OTT_trend);

   // ── Minor trend (3.5)
   double OTT_minor[];
   ComputeOTT(VAR_trend, total, MinorPercent, OTT_minor);

   // ── Bölge: TOTT
   double OTT_zone_local[];
   ComputeOTT(VAR_trend, total, TottPercent, OTT_zone_local);
   ArrayResize(OTTup_zone, total); ArrayResize(OTTdn_zone, total);
   for(int i=0;i<total;i++) {
      OTTup_zone[i] = (OTT_zone_local[i]!=EMPTY_VALUE) ? OTT_zone_local[i]*(1+TottCoeff) : EMPTY_VALUE;
      OTTdn_zone[i] = (OTT_zone_local[i]!=EMPTY_VALUE) ? OTT_zone_local[i]*(1-TottCoeff) : EMPTY_VALUE;
   }

   // ── Bölge: SOTT
   double stoch[], stoch_smoothed[], sott_src[];
   ComputeStoch(cl, hi, lo, total, SottPeriodK, stoch);
   ComputeVAR(stoch, total, SottSmoothK, stoch_smoothed);
   ArrayResize(sott_src, total);
   for(int i=0;i<total;i++)
      sott_src[i] = (stoch_smoothed[i]!=EMPTY_VALUE) ? stoch_smoothed[i]+1000 : EMPTY_VALUE;
   ComputeOTT(sott_src, total, SottPercent, SOTT_ott);

   // ── Kapı: HOTT/LOTT
   ComputeHOTT(hi, total, GateLength, GatePercent, HOTT_line);
   ComputeLOTT(lo, total, GateLength, GatePercent, LOTT_line);

   // ── ROTT yaması
   double rott_ma2[];
   ComputeVAR(cl, total, RottX2, rott_ma2);
   for(int i=0;i<total;i++) if(rott_ma2[i]!=EMPTY_VALUE) rott_ma2[i] *= 2;
   ComputeOTT(rott_ma2, total, RottPercent, ROTT_ott);
   ArrayCopy(ROTT_ma, rott_ma2);

   // ── Sinyal değerlendirmesi (shift_eval kadar geriye)
   int eval_idx = total - 1 - shift_eval;
   if(eval_idx < 1) return false;

   double mavg     = VAR_trend[eval_idx];
   double trendOtt = OTT_trend[eval_idx];
   double minorOtt = OTT_minor[eval_idx];
   double tottUp   = OTTup_zone[eval_idx];
   double tottDn   = OTTdn_zone[eval_idx];
   double sottSrc  = sott_src[eval_idx];
   double sottOtt  = SOTT_ott[eval_idx];
   double hottLine = HOTT_line[eval_idx];
   double lottLine = LOTT_line[eval_idx];
   double rottMa   = ROTT_ma[eval_idx];
   double rottLine = ROTT_ott[eval_idx];
   double curHigh  = hi[eval_idx];
   double curLow   = lo[eval_idx];

   if(mavg==EMPTY_VALUE || trendOtt==EMPTY_VALUE || tottUp==EMPTY_VALUE ||
      sottSrc==EMPTY_VALUE || sottOtt==EMPTY_VALUE ||
      hottLine==EMPTY_VALUE || lottLine==EMPTY_VALUE ||
      rottMa==EMPTY_VALUE || rottLine==EMPTY_VALUE)
      return false;

   bool majorUp = mavg > trendOtt;
   bool majorDn = mavg < trendOtt;
   bool minorUp = mavg > minorOtt;
   bool minorDn = mavg < minorOtt;
   bool tottZoneUp = mavg > tottUp;
   bool tottZoneDn = mavg < tottDn;
   bool sottUp = sottSrc > sottOtt;
   bool sottDn = sottSrc < sottOtt;
   bool zoneUp = tottZoneUp && sottUp;
   bool zoneDn = tottZoneDn && sottDn;

   // HOTT/LOTT: H > line AND H > REF(HHV(H,N),-1)
   double hhv_prev = hi[eval_idx-1];
   int start_h = MathMax(0, eval_idx - GateLength);
   for(int k=start_h; k<eval_idx; k++) if(hi[k] > hhv_prev) hhv_prev = hi[k];
   bool hottOk = (curHigh > hottLine) && (curHigh > hhv_prev);

   double llv_prev = lo[eval_idx-1];
   int start_l = MathMax(0, eval_idx - GateLength);
   for(int k=start_l; k<eval_idx; k++) if(lo[k] < llv_prev) llv_prev = lo[k];
   bool lottOk = (curLow < lottLine) && (curLow < llv_prev);

   bool rottUp = rottMa > rottLine;
   bool rottDn = rottMa < rottLine;

   // AL şartı
   bool al_main_up = zoneUp && hottOk;
   bool al_main_dn = minorUp && zoneUp && hottOk;
   buyLong = ((majorUp && al_main_up) || (majorDn && al_main_dn)) && rottUp;

   // SAT (long çıkış)
   exitLong = zoneDn && lottOk;

   // AÇIĞA SAT
   bool as_main_dn = zoneDn && lottOk;
   bool as_main_up = minorDn && zoneDn && lottOk;
   buyShort = ((majorDn && as_main_dn) || (majorUp && as_main_up)) && rottDn;

   // AÇIK POZ KAPAT
   exitShort = zoneUp && hottOk;

   return true;
}

//+------------------------------------------------------------------+
//| Trade yardımcıları                                                |
//+------------------------------------------------------------------+
int  CountOpenPositions(int type)
{
   int c = 0;
   for(int i=OrdersTotal()-1; i>=0; i--) {
      if(!OrderSelect(i, SELECT_BY_POS)) continue;
      if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber && OrderType() == type)
         c++;
   }
   return c;
}

void CloseAllByType(int type)
{
   for(int i=OrdersTotal()-1; i>=0; i--) {
      if(!OrderSelect(i, SELECT_BY_POS)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;
      if(OrderType() != type) continue;
      double price = (type == OP_BUY) ? Bid : Ask;
      if(!OrderClose(OrderTicket(), OrderLots(), price, Slippage, clrYellow))
         Print("OrderClose hata: ", GetLastError());
   }
}

bool OpenPosition(int type)
{
   double price = (type == OP_BUY) ? Ask : Bid;
   int ticket = OrderSend(Symbol(), type, LotSize, price, Slippage, 0, 0,
                          "OTT EA", MagicNumber, 0,
                          (type==OP_BUY) ? clrGreen : clrRed);
   if(ticket < 0) { Print("OrderSend hata: ", GetLastError()); return false; }
   return true;
}

bool InTimeWindow()
{
   if(!UseTimeFilter) return true;
   int h = TimeHour(TimeCurrent());
   return (h >= StartHour && h < EndHour);
}

//+------------------------------------------------------------------+
void OnTick()
{
   // sadece yeni bar açılışında çalış (sinyal kararı önceki kapanmış bar üzerinde)
   if(Time[0] == lastBarTime) return;
   lastBarTime = Time[0];

   if(!InTimeWindow()) return;
   if(!CheckRiskLimits()) return;

   bool buyL, exitL, buyS, exitS;
   if(!ComputeSignals(1, buyL, exitL, buyS, exitS)) return;
   // shift_eval=1 yani SON KAPANMIŞ bar'ın sinyali

   int openLong  = CountOpenPositions(OP_BUY);
   int openShort = CountOpenPositions(OP_SELL);

   // Kapanışlar önce
   if(openLong  > 0 && exitL) CloseAllByType(OP_BUY);
   if(openShort > 0 && exitS) CloseAllByType(OP_SELL);

   // Flip — buyL True iken short açık ise kapat, sonra long aç
   openLong  = CountOpenPositions(OP_BUY);
   openShort = CountOpenPositions(OP_SELL);
   if(openShort > 0 && buyL) CloseAllByType(OP_SELL);
   if(openLong  > 0 && buyS) CloseAllByType(OP_BUY);

   openLong  = CountOpenPositions(OP_BUY);
   openShort = CountOpenPositions(OP_SELL);

   if(AllowLong  && openLong  == 0 && buyL) OpenPosition(OP_BUY);
   if(AllowShort && openShort == 0 && buyS) OpenPosition(OP_SELL);
}
//+------------------------------------------------------------------+
