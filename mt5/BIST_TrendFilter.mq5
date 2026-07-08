//+------------------------------------------------------------------+
//|  BIST_TrendFilter.mq5                                            |
//|  OTT + EMA + ADX çift-teyitli trend filtresi (long-or-flat)      |
//|                                                                  |
//|  MANTIK (26 yıl BIST'te doğrulandı — research_mix.py):           |
//|   LONG aç  = close>OTT VE close>EMA19 VE ADX>18 VE +DI>-DI       |
//|   KAPAT    = bu koşullardan biri bozulunca (flat'e geç = "nakit")|
//|  Sonuç: buy&hold benzeri getiri, MaxDD %69→%16, Sharpe 2.83.     |
//|  Bu ALFA DEĞİL, RİSK YÖNETİMİ: düşüşte pozisyonu kapatıp korur.  |
//|  Grid'den TAMAMEN farklı: düşük frekans (günde 1 kez, D1 bar).   |
//+------------------------------------------------------------------+
#property strict
#include <Trade/Trade.mqh>
CTrade trade;

input ENUM_TIMEFRAMES InpTF          = PERIOD_D1;   // Zaman dilimi (test: D1)
input int    InpOTTLength            = 40;          // OTT VAR periyodu
input double InpOTTPercent           = 2.0;         // OTT % bandı
input int    InpEMA                  = 19;          // EMA periyodu
input int    InpADXPeriod            = 14;          // ADX periyodu
input double InpADXThreshold         = 18.0;        // ADX eşiği (trend gücü)
input double InpUnitPct              = 8.0;         // Sembol başı notional = kasanın %X'i
input double InpMaxSymbolPct         = 8.0;         // Sembol başı tavan (tek pozisyon)
input double InpSafeReservePct       = 20.0;        // GLOBAL: %X hep güvende → max %80 açık
input bool   InpScanAll              = true;        // Tüm F_ hisse futures'larını tara
input string InpSymbols              = "";          // Elle liste (ScanAll=false ise)
input long   InpMagic                = 20260201;    // Sihirli sayı (grid'den AYRI)
input int    InpTimerSec             = 30;          // Kontrol aralığı (sn)
input bool   InpVerbose              = true;

string   g_symbols[];
datetime g_lastBar[];

//+------------------------------------------------------------------+
// SADECE BIST tek-hisse futures'ı? (döviz/emtia/endeks hariç)
bool IsEquityFut(const string nm)
{
   if(StringFind(nm, "F_") != 0) return false;
   string bad[] = {"USD","EUR","GBP","XAU","XAG","XPT","XPD","TRYM","XU0","XU1"};
   for(int i=0;i<ArraySize(bad);i++)
      if(StringFind(nm, bad[i]) >= 0) return false;
   return true;
}

//+------------------------------------------------------------------+
//| VAR (VIDYA) hareketli ortalama — Anıl Özekşi (indicators.py portu)|
//+------------------------------------------------------------------+
void ComputeVAR(const double &close[], int n, int length, double &out[])
{
   ArrayResize(out, n); ArrayInitialize(out, EMPTY_VALUE);
   if(length<=1){ for(int i=0;i<n;i++) out[i]=close[i]; return; }
   double alpha = 2.0/(length+1.0);
   // CMO_9 |.| ∈[0,1]
   double up[], dn[]; ArrayResize(up,n); ArrayResize(dn,n);
   up[0]=0; dn[0]=0;
   for(int i=1;i<n;i++){ double d=close[i]-close[i-1]; up[i]=(d>0?d:0); dn[i]=(d<0?-d:0); }
   double vidya=EMPTY_VALUE; bool started=false;
   for(int i=0;i<n;i++)
   {
      double su=0,sd=0;
      if(i>=8){ for(int k=i-8;k<=i;k++){ su+=up[k]; sd+=dn[k]; } }
      double denom=su+sd;
      double cmo = (denom>0 ? MathAbs((su-sd)/denom) : 0.0);
      if(!started)
      {
         if(i>=length-1)   // ilk SMA
         {
            double s=0; for(int k=i-length+1;k<=i;k++) s+=close[k];
            vidya=s/length; out[i]=vidya; started=true;
         }
         continue;
      }
      vidya = cmo*alpha*(close[i]-vidya) + vidya;
      out[i]=vidya;
   }
}

//+------------------------------------------------------------------+
//| OTT çizgisi (_ott_loop portu). ott[i], shift UYGULANMADAN.        |
//+------------------------------------------------------------------+
void ComputeOTT(const double &close[], int n, int length, double percent, double &ott[])
{
   double mavg[]; ComputeVAR(close, n, length, mavg);
   ArrayResize(ott, n); ArrayInitialize(ott, EMPTY_VALUE);
   double ls_prev=EMPTY_VALUE, ss_prev=EMPTY_VALUE; int dir_prev=1;
   for(int i=0;i<n;i++)
   {
      if(mavg[i]==EMPTY_VALUE) continue;
      double fark = mavg[i]*percent*0.01;
      double ls = mavg[i]-fark, ss = mavg[i]+fark;
      if(ls_prev==EMPTY_VALUE) ls_prev=ls;
      if(ss_prev==EMPTY_VALUE) ss_prev=ss;
      if(mavg[i]>ls_prev && ls<ls_prev) ls=ls_prev;
      if(mavg[i]<ss_prev && ss>ss_prev) ss=ss_prev;
      int d;
      if(dir_prev==-1 && mavg[i]>ss_prev) d=1;
      else if(dir_prev==1 && mavg[i]<ls_prev) d=-1;
      else d=dir_prev;
      double mt = (d==1? ls : ss);
      ott[i] = (mavg[i]>mt ? mt*(200+percent)/200.0 : mt*(200-percent)/200.0);
      ls_prev=ls; ss_prev=ss; dir_prev=d;
   }
}

//+------------------------------------------------------------------+
//| EMA (span=period) — son değer                                     |
//+------------------------------------------------------------------+
double ComputeEMA(const double &close[], int n, int period)
{
   if(n<period) return EMPTY_VALUE;
   double a=2.0/(period+1.0), ema=close[0];
   for(int i=1;i<n;i++) ema = a*close[i] + (1-a)*ema;
   return ema;
}

//+------------------------------------------------------------------+
//| ADX (Wilder) — son adx, +DI, -DI                                  |
//+------------------------------------------------------------------+
void ComputeADX(const double &h[], const double &l[], const double &c[], int n, int period,
                double &adx_out, double &pdi_out, double &mdi_out)
{
   adx_out=EMPTY_VALUE; pdi_out=0; mdi_out=0;
   if(n<period*3) return;
   double a=1.0/period;
   double atr=0,pdm=0,mdm=0, pdi=0,mdi=0, adx=0; bool init=false;
   for(int i=1;i<n;i++)
   {
      double tr=MathMax(h[i]-l[i], MathMax(MathAbs(h[i]-c[i-1]), MathAbs(l[i]-c[i-1])));
      double up=h[i]-h[i-1], dn=l[i-1]-l[i];
      double p=((up>dn && up>0)? up:0), m=((dn>up && dn>0)? dn:0);
      if(!init){ atr=tr; pdm=p; mdm=m; init=true; continue; }
      atr = a*tr + (1-a)*atr;
      pdm = a*p  + (1-a)*pdm;
      mdm = a*m  + (1-a)*mdm;
      pdi = (atr>0? 100*pdm/atr:0);
      mdi = (atr>0? 100*mdm/atr:0);
      double dx = ((pdi+mdi)>0? 100*MathAbs(pdi-mdi)/(pdi+mdi):0);
      adx = (i==1? dx : a*dx + (1-a)*adx);
   }
   adx_out=adx; pdi_out=pdi; mdi_out=mdi;
}

//+------------------------------------------------------------------+
int OnInit()
{
   int n=0;
   if(InpScanAll)
   {
      int all=SymbolsTotal(false), eklenen=0;
      for(int i=0;i<all;i++){ string nm=SymbolName(i,false);
         if(IsEquityFut(nm)) if(SymbolSelect(nm,true)) eklenen++; }
      if(eklenen>0) PrintFormat("Market Watch'a %d BIST hisse futures eklendi", eklenen);
      int tot=SymbolsTotal(true); ArrayResize(g_symbols,tot);
      for(int i=0;i<tot;i++){ string nm=SymbolName(i,true); if(IsEquityFut(nm)) g_symbols[n++]=nm; }
      ArrayResize(g_symbols,n);
   }
   else n=StringSplit(InpSymbols, ',', g_symbols);
   if(n<=0){ Print("HATA: sembol yok"); return INIT_FAILED; }
   ArrayResize(g_lastBar,n);
   for(int i=0;i<n;i++){ StringTrimLeft(g_symbols[i]); StringTrimRight(g_symbols[i]);
      SymbolSelect(g_symbols[i],true); g_lastBar[i]=0; }
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(30);
   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   PrintFormat("BIST TREND-FİLTRE başladı · %d sembol · TF=%s · OTT(%d,%.1f)+EMA%d+ADX>%.0f · birim %%%.0f · max %%%.0f açık",
      n, EnumToString(InpTF), InpOTTLength, InpOTTPercent, InpEMA, InpADXThreshold,
      InpUnitPct, 100.0-InpSafeReservePct);
   EventSetTimer(MathMax(5,InpTimerSec));
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason){ EventKillTimer(); }
void OnTick(){}

//+------------------------------------------------------------------+
double TotalNotional()
{
   double tot=0;
   for(int i=PositionsTotal()-1;i>=0;i--){ ulong tk=PositionGetTicket(i);
      if(!tk||!PositionSelectByTicket(tk)) continue;
      if(PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      string s=PositionGetString(POSITION_SYMBOL);
      tot+=PositionGetDouble(POSITION_VOLUME)*PositionGetDouble(POSITION_PRICE_CURRENT)
           *SymbolInfoDouble(s,SYMBOL_TRADE_CONTRACT_SIZE); }
   return tot;
}
bool HasPos(string sym)
{
   for(int i=PositionsTotal()-1;i>=0;i--){ ulong tk=PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==sym &&
         PositionGetInteger(POSITION_MAGIC)==InpMagic) return true; }
   return false;
}
void CloseSym(string sym)
{
   for(int i=PositionsTotal()-1;i>=0;i--){ ulong tk=PositionGetTicket(i);
      if(!tk||!PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL)==sym && PositionGetInteger(POSITION_MAGIC)==InpMagic)
         trade.PositionClose(tk); }
}
double CalcLots(string sym, double ask)
{
   if(SymbolInfoInteger(sym,SYMBOL_TRADE_MODE)!=SYMBOL_TRADE_MODE_FULL) return 0;
   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   double budget=eq*(100.0-InpSafeReservePct)/100.0 - TotalNotional();
   if(budget<=0) return 0;
   double target=MathMin(eq*InpUnitPct/100.0, MathMin(budget, eq*InpMaxSymbolPct/100.0));
   double cs=SymbolInfoDouble(sym,SYMBOL_TRADE_CONTRACT_SIZE);
   if(cs<=0||ask<=0) return 0;
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP), minl=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN),
          maxl=SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX);
   if(step<=0) step=minl;
   double lots=MathFloor((target/(ask*cs))/step)*step;
   if(lots<minl) return 0;
   if(lots>maxl) lots=maxl;
   double need=0;
   if(OrderCalcMargin(ORDER_TYPE_BUY,sym,lots,ask,need))
      if(need>AccountInfoDouble(ACCOUNT_MARGIN_FREE)*0.98) return 0;
   int vd=(step>=1.0)?0:(int)MathRound(-MathLog10(step));
   return NormalizeDouble(lots,vd);
}

//+------------------------------------------------------------------+
//| Sinyal: OTT VE EMA VE ADX birlikte yukarı mı?                     |
//+------------------------------------------------------------------+
bool LongSignal(string sym)
{
   int need=InpOTTLength + InpADXPeriod*3 + 10;
   MqlRates r[]; ArraySetAsSeries(r,false);
   int got=CopyRates(sym, InpTF, 0, need, r);
   if(got<need-5) return false;
   int m=got;
   double cl[],hi[],lo[]; ArrayResize(cl,m);ArrayResize(hi,m);ArrayResize(lo,m);
   for(int i=0;i<m;i++){ cl[i]=r[i].close; hi[i]=r[i].high; lo[i]=r[i].low; }
   // OTT (shift 2 → close[last] vs ott[last-2])
   double ott[]; ComputeOTT(cl,m,InpOTTLength,InpOTTPercent,ott);
   int last=m-1;
   if(last-2<0 || ott[last-2]==EMPTY_VALUE) return false;
   double ema=ComputeEMA(cl,m,InpEMA);
   double adx,pdi,mdi; ComputeADX(hi,lo,cl,m,InpADXPeriod,adx,pdi,mdi);
   if(ema==EMPTY_VALUE || adx==EMPTY_VALUE) return false;
   double c=cl[last];
   return (c>ott[last-2] && c>ema && adx>InpADXThreshold && pdi>mdi);
}

//+------------------------------------------------------------------+
void OnTimer()
{
   int n=ArraySize(g_symbols), nLong=0, nData=0;
   for(int s=0;s<n;s++)
   {
      string sym=g_symbols[s];
      // sadece YENİ D1 bar'da değerlendir (düşük frekans, gün içi churn yok)
      datetime bt=(datetime)SeriesInfoInteger(sym, InpTF, SERIES_LASTBAR_DATE);
      if(bt==0) continue;
      nData++;
      if(bt==g_lastBar[s]) continue;   // bu bar zaten işlendi
      bool longOK=LongSignal(sym);
      if(longOK) nLong++;
      bool have=HasPos(sym);
      if(longOK && !have)
      {
         double ask=SymbolInfoDouble(sym,SYMBOL_ASK);
         if(ask>0){ double lots=CalcLots(sym,ask);
            if(lots>0){ if(trade.Buy(lots,sym,ask,0,0,"TF"))
               { if(InpVerbose) PrintFormat("✅ LONG: %s @ %.4g · %.2f lot (OTT+EMA+ADX teyitli)",sym,ask,lots); }
               else PrintFormat("❌ AL HATA: %s ret=%d %s",sym,trade.ResultRetcode(),trade.ResultRetcodeDescription()); } }
      }
      else if(!longOK && have)
      {
         CloseSym(sym);
         if(InpVerbose) PrintFormat("🔻 KAPAT (trend bozuldu): %s → nakit",sym);
      }
      g_lastBar[s]=bt;
   }
   static datetime lastReport=0;
   if(TimeCurrent()-lastReport>=300)
   {
      double eq=AccountInfoDouble(ACCOUNT_EQUITY);
      PrintFormat("TANI: veri %d · LONG-sinyal %d · açık %d · kasa %%%.0f",
         nData, nLong, PositionsTotal(), (eq>0? (eq-TotalNotional())/eq*100.0:0));
      lastReport=TimeCurrent();
   }
}
//+------------------------------------------------------------------+
