//+------------------------------------------------------------------+
//|                                              BIST_Grid.mq5        |
//|  KANITLANMIŞ BIST GRID — yatay-kapılı, TRAILING çıkış, long-only  |
//|  ÇOKLU SEMBOL: tüm Market Watch'ı tarar (InpScanAll).             |
//|  Kaufman ER<0.30 = yatay → grid; trend → kapat. Seviye -1/-2/-3%. |
//|  Birim +%1.5'te trailing aktif, peak'in %0.5 altına inince sat.   |
//|  💰 KASA KORUMA: öz sermayenin %20'si HER ZAMAN güvende (GLOBAL) —|
//|     tüm sembollerdeki toplam notional ≤ %80. Kaldıraç YOK. DEMO.  |
//+------------------------------------------------------------------+
#property copyright "OTT Bot — QUANT DESK"
#property version   "2.00"
#property strict
#include <Trade/Trade.mqh>

//============================ GİRDİLER ==============================
input bool    InpScanAll          = true;     // TÜM Market Watch sembollerini tara
input string  InpSymbols          = "GARAN,THYAO,ASELS,EREGL,SISE,KCHOL,AKBNK,SASA,TUPRS,FROTO"; // ScanAll=false ise
input ENUM_TIMEFRAMES InpTF        = PERIOD_H1; // Zaman dilimi (sistem H1)
input int     InpER_Win           = 20;      // Kaufman ER penceresi
input double  InpER_Th            = 0.30;     // ER < bu = YATAY (grid açık)
input double  InpLevel1Pct        = 1.0;      // 1. AL seviyesi: SMA20 -% (BIST sıkı)
input double  InpLevel2Pct        = 2.0;      // 2. AL seviyesi
input double  InpLevel3Pct        = 3.0;      // 3. AL seviyesi
input double  InpTakePct          = 1.5;      // +%X'te TRAILING aktifleş
input double  InpTrailPct         = 0.5;      // peak'in %X altına inince sat
input double  InpUnitPct          = 5.0;      // Birim başı notional (% öz sermaye) — çok sembolde küçük tut
input double  InpSafeReservePct   = 20.0;     // 💰 %X HER ZAMAN güvende (GLOBAL) → toplam ≤ %80
input long    InpMagic            = 20260103;
input int     InpTimerSec         = 10;       // Tarama aralığı (sn)
input bool    InpVerbose          = true;

//============================ GLOBAL ===============================
CTrade    trade;
string    g_symbols[];
datetime  g_lastBar[];
double    g_levels[3];

//+------------------------------------------------------------------+
int OnInit()
{
   int n = 0;
   if(InpScanAll)
   {
      int tot = SymbolsTotal(true);
      ArrayResize(g_symbols, tot);
      for(int i=0;i<tot;i++) g_symbols[i] = SymbolName(i, true);
      n = tot;
   }
   else n = StringSplit(InpSymbols, ',', g_symbols);
   if(n <= 0){ Print("HATA: taranacak sembol yok."); return INIT_FAILED; }

   ArrayResize(g_lastBar, n);
   for(int i=0;i<n;i++)
   {
      StringTrimLeft(g_symbols[i]); StringTrimRight(g_symbols[i]);
      SymbolSelect(g_symbols[i], true);
      g_lastBar[i] = 0;
   }
   g_levels[0]=InpLevel1Pct; g_levels[1]=InpLevel2Pct; g_levels[2]=InpLevel3Pct;
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(30);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   PrintFormat("BIST GRID (çoklu) başladı · %d sembol · TF=%s · ER<%.2f · AL -%.0f/-%.0f/-%.0f%% · trailing +%.1f/%.1f%% · birim %%%.0f · KASA %.0f (%%%.0f güvende → max %%%.0f)",
               n, EnumToString(InpTF), InpER_Th, InpLevel1Pct, InpLevel2Pct, InpLevel3Pct,
               InpTakePct, InpTrailPct, InpUnitPct, eq, InpSafeReservePct, 100.0-InpSafeReservePct);
   EventSetTimer(MathMax(2, InpTimerSec));
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason){ EventKillTimer(); }
void OnTick(){ }   // ana mantık OnTimer'da (çoklu sembol)

//+------------------------------------------------------------------+
bool GetRegime(string sym, double &er, double &center)
{
   int need = InpER_Win + 2;
   double cl[]; ArraySetAsSeries(cl, false);
   if(CopyClose(sym, InpTF, 0, need, cl) < need) return false;
   int last = need - 2;
   double net = MathAbs(cl[last] - cl[last - InpER_Win]);
   double vol = 0;
   for(int i=last-InpER_Win+1; i<=last; i++) vol += MathAbs(cl[i]-cl[i-1]);
   er = (vol > 0) ? net/vol : 1.0;
   double sum = 0; for(int i=last-InpER_Win+1; i<=last; i++) sum += cl[i];
   center = sum / InpER_Win;
   return true;
}

//+------------------------------------------------------------------+
//| GLOBAL kasa koruma: tüm sembollerdeki magic notional toplamı     |
//+------------------------------------------------------------------+
double TotalNotional()
{
   double tot = 0;
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk==0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      string s = PositionGetString(POSITION_SYMBOL);
      tot += PositionGetDouble(POSITION_VOLUME) * PositionGetDouble(POSITION_PRICE_CURRENT)
             * SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE);
   }
   return tot;
}

bool LevelHeld(string sym, int k)
{
   string tag = "G" + IntegerToString(k);
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==sym &&
         PositionGetInteger(POSITION_MAGIC)==InpMagic &&
         PositionGetString(POSITION_COMMENT)==tag) return true;
   }
   return false;
}

int OpenCount(string sym)
{
   int c=0;
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==sym && PositionGetInteger(POSITION_MAGIC)==InpMagic) c++;
   }
   return c;
}

void CloseSym(string sym, string why)
{
   int closed=0;
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==sym && PositionGetInteger(POSITION_MAGIC)==InpMagic)
         { if(trade.PositionClose(tk)) closed++; }
   }
   if(InpVerbose && closed>0) PrintFormat("Grid kapatıldı (%s): %d birim · %s", sym, closed, why);
}

//+------------------------------------------------------------------+
double CalcLots(string sym, double ask)
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double usable = eq * (100.0 - InpSafeReservePct) / 100.0;     // %80 GLOBAL
   double budget = usable - TotalNotional();                     // kalan global bütçe
   if(budget <= 0) return 0;                                     // kasa korumalı: dur
   double target = MathMin(eq * InpUnitPct/100.0, budget);       // birim = %5 eq, bütçeyle sınırlı
   double cs = SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE);
   if(cs<=0 || ask<=0) return 0;
   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double minl = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double maxl = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   if(step<=0) step=minl;
   double lots = MathFloor((target/(ask*cs))/step)*step;
   if(lots < minl) return 0;
   if(lots > maxl) lots = maxl;
   double need=0;
   if(OrderCalcMargin(ORDER_TYPE_BUY, sym, lots, ask, need))
      if(need > AccountInfoDouble(ACCOUNT_MARGIN_FREE)*0.98) return 0;
   int vd = (step>=1.0)?0:(int)MathRound(-MathLog10(step));
   return NormalizeDouble(lots, vd);
}

//+------------------------------------------------------------------+
void TrailSym(string sym)
{
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   int dg = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk==0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=sym || PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      if((bid-entry)/entry < InpTakePct/100.0) continue;          // +%1.5'e ulaşmadı
      double desiredSL = bid * (1.0 - InpTrailPct/100.0);
      double curSL = PositionGetDouble(POSITION_SL);
      if(curSL==0 || desiredSL > curSL)
         trade.PositionModify(tk, NormalizeDouble(desiredSL, dg), PositionGetDouble(POSITION_TP));
   }
}

//+------------------------------------------------------------------+
void OnTimer()
{
   int n = ArraySize(g_symbols);
   for(int s=0; s<n; s++)
   {
      string sym = g_symbols[s];
      double er, center;
      if(!GetRegime(sym, er, center)) continue;
      bool sideways = (er < InpER_Th);
      datetime bt = iTime(sym, InpTF, 0);
      if(bt==0) continue;
      bool newbar = (bt != g_lastBar[s]);

      if(!sideways)
      {
         if(newbar && OpenCount(sym)>0) CloseSym(sym, StringFormat("TREND (ER=%.2f)", er));
         g_lastBar[s] = bt;
         continue;
      }
      TrailSym(sym);                                              // açık birimleri trailing'le yönet

      double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
      if(ask<=0){ g_lastBar[s]=bt; continue; }
      for(int k=0;k<3;k++)
      {
         double lvl = center * (1.0 - g_levels[k]/100.0);
         if(ask <= lvl && !LevelHeld(sym, k+1))
         {
            double lots = CalcLots(sym, ask);
            if(lots <= 0) continue;                               // kasa koruması/bütçe doldu
            if(trade.Buy(lots, sym, ask, 0, 0, "G"+IntegerToString(k+1)))
            {
               if(InpVerbose)
               {
                  double eq=AccountInfoDouble(ACCOUNT_EQUITY);
                  PrintFormat("GRID AL: %s sev%d @ %.4g · %.2f lot · kasa %%%.0f kullanımda",
                              sym, k+1, ask, lots, TotalNotional()/eq*100.0);
               }
            }
         }
      }
      g_lastBar[s] = bt;
      Sleep(5);
   }
}
//+------------------------------------------------------------------+
