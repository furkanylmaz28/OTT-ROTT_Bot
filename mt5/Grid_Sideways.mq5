//+------------------------------------------------------------------+
//|                                          Grid_Sideways.mq5        |
//|   Kanıtlanmış 2. sistem: YATAY-KAPILI GRID (long-only)           |
//|   Kaufman ER ile rejim: ER<eşik=yatay → grid açık; trend → kapat |
//|   WF 8/8 OOS+, MC medyan +62% (BIST). GOLD'da KALDIRACA DİKKAT.  |
//+------------------------------------------------------------------+
#property copyright "OTT Bot"
#property version   "1.00"
#property strict
#include <Trade/Trade.mqh>

//============================ GİRDİLER ==============================
input string  InpSymbol         = "";          // Boş = grafik sembolü (XAUUSD için boş bırak)
input ENUM_TIMEFRAMES InpTF      = PERIOD_H1;   // Zaman dilimi (sistem H1)
input int     InpER_Win          = 20;          // Efficiency Ratio penceresi
input double  InpER_Th           = 0.30;        // ER < bu = YATAY (grid açık)
input double  InpLevel1Pct       = 2.0;         // 1. AL seviyesi: merkez -%
input double  InpLevel2Pct       = 4.0;         // 2. AL seviyesi
input double  InpLevel3Pct       = 6.0;         // 3. AL seviyesi
input double  InpTakePct         = 2.0;         // Her birim +%X'te sat (TP)
input double  InpMarginPerUnitPct = 1.0;        // Birim başı teminat (% öz sermaye) — GOLD'da DÜŞÜK TUT!
input long    InpMagic           = 20260102;
input bool    InpVerbose         = true;

//============================ GLOBAL ===============================
CTrade    trade;
string    g_sym;
datetime  g_lastBar = 0;
double    g_levels[3];

//+------------------------------------------------------------------+
int OnInit()
{
   g_sym = (InpSymbol == "") ? _Symbol : InpSymbol;
   if(!SymbolSelect(g_sym, true)){ Print("HATA: sembol yok -> ", g_sym); return INIT_FAILED; }
   g_levels[0] = InpLevel1Pct; g_levels[1] = InpLevel2Pct; g_levels[2] = InpLevel3Pct;
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(30);
   trade.SetTypeFillingBySymbol(g_sym);
   PrintFormat("Grid Sideways başladı · %s · TF=%s · ER<%.2f · AL -%.0f/-%.0f/-%.0f%% · TP +%.0f%% · birim %%%.1f teminat",
               g_sym, EnumToString(InpTF), InpER_Th, InpLevel1Pct, InpLevel2Pct, InpLevel3Pct,
               InpTakePct, InpMarginPerUnitPct);
   Print("UYARI: GOLD CFD native kaldıraç ~100x. Birim %%1 teminat ≈ uygun. Log'daki kaldıraca bak!");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason){}

//+------------------------------------------------------------------+
//| Kaufman ER + SMA hesapla (son kapanan bara kadar)               |
//+------------------------------------------------------------------+
bool GetRegime(double &er, double &center)
{
   int need = InpER_Win + 2;
   double cl[]; ArraySetAsSeries(cl, false);
   if(CopyClose(g_sym, InpTF, 0, need, cl) < need) return false;
   // son kapanan bar = need-2 (need-1 oluşan bar)
   int last = need - 2;
   double net = MathAbs(cl[last] - cl[last - InpER_Win]);
   double vol = 0;
   for(int i = last - InpER_Win + 1; i <= last; i++) vol += MathAbs(cl[i] - cl[i-1]);
   er = (vol > 0) ? net / vol : 1.0;
   double sum = 0; for(int i = last - InpER_Win + 1; i <= last; i++) sum += cl[i];
   center = sum / InpER_Win;
   return true;
}

//+------------------------------------------------------------------+
int UnitCount()
{
   int c = 0;
   for(int i = PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==g_sym && PositionGetInteger(POSITION_MAGIC)==InpMagic) c++;
   }
   return c;
}

bool LevelHeld(int k)
{
   string tag = "G" + IntegerToString(k);
   for(int i = PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==g_sym &&
         PositionGetInteger(POSITION_MAGIC)==InpMagic &&
         PositionGetString(POSITION_COMMENT)==tag) return true;
   }
   return false;
}

void CloseAll(string why)
{
   for(int i = PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==g_sym && PositionGetInteger(POSITION_MAGIC)==InpMagic)
         trade.PositionClose(tk);
   }
   if(InpVerbose) Print("Grid kapatıldı: ", why);
}

double CalcLots()
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double target_margin = eq * (InpMarginPerUnitPct / 100.0);
   double ask = SymbolInfoDouble(g_sym, SYMBOL_ASK);
   double m1 = 0;
   if(!OrderCalcMargin(ORDER_TYPE_BUY, g_sym, 1.0, ask, m1) || m1 <= 0) return 0;
   double step = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_STEP);
   double minl = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_MIN);
   double maxl = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_MAX);
   if(step <= 0) step = minl;
   double lots = MathFloor((target_margin / m1) / step) * step;
   if(lots < minl) return 0;
   if(lots > maxl) lots = maxl;
   return NormalizeDouble(lots, 2);
}

//+------------------------------------------------------------------+
void OnTick()
{
   double er, center;
   if(!GetRegime(er, center)) return;

   bool sideways = (er < InpER_Th);
   datetime bt = iTime(g_sym, InpTF, 0);
   bool newbar = (bt != g_lastBar);

   // Trend rejimi → tüm grid birimlerini kapat (yeni barda bir kez)
   if(!sideways)
   {
      if(newbar && UnitCount() > 0) CloseAll(StringFormat("TREND (ER=%.2f)", er));
      g_lastBar = bt;
      return;
   }

   // YATAY → grid: fiyat seviyeye inerse, o seviye boşsa AL (+TP)
   double ask = SymbolInfoDouble(g_sym, SYMBOL_ASK);
   for(int k=0;k<3;k++)
   {
      double lvl = center * (1.0 - g_levels[k]/100.0);
      if(ask <= lvl && !LevelHeld(k+1))
      {
         double lots = CalcLots();
         if(lots <= 0) continue;
         double tp = ask * (1.0 + InpTakePct/100.0);
         if(trade.Buy(lots, g_sym, ask, 0, tp, "G" + IntegerToString(k+1)))
         {
            if(InpVerbose)
            {
               double cs = SymbolInfoDouble(g_sym, SYMBOL_TRADE_CONTRACT_SIZE);
               double notional = lots * ask * cs;
               PrintFormat("GRID AL: seviye %d @ %.2f · %.2f lot · TP %.2f · ~%.1fx kaldıraç",
                           k+1, ask, lots, tp, notional/AccountInfoDouble(ACCOUNT_EQUITY));
            }
         }
      }
   }
   g_lastBar = bt;
}
//+------------------------------------------------------------------+
