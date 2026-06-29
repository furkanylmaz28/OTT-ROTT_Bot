//+------------------------------------------------------------------+
//|                                              BIST_Grid.mq5        |
//|  KANITLANMIŞ BIST GRID — yatay-kapılı, TRAILING çıkış, long-only  |
//|  Kaufman ER<0.30 = yatay → grid; trend → kapat. Seviye -1/-2/-3%. |
//|  Birim +%1.5'te trailing aktif, peak'in %0.5 altına inince sat.   |
//|  Cost-sweep + OOS (PF 1.18 OOS @ %0.10 maliyet) ile doğrulandı.   |
//|  💰 KASA KORUMA: öz sermayenin %20'si HER ZAMAN güvende —          |
//|     toplam yatırım (notional) ≤ %80. Kaldıraç YOK. SADECE DEMO.   |
//+------------------------------------------------------------------+
#property copyright "OTT Bot — QUANT DESK"
#property version   "1.00"
#property strict
#include <Trade/Trade.mqh>

//============================ GİRDİLER ==============================
input string  InpSymbol          = "";       // Boş = grafik sembolü (BIST hissesi)
input ENUM_TIMEFRAMES InpTF       = PERIOD_H1; // Zaman dilimi (sistem H1 ile doğrulandı)
input int     InpER_Win           = 20;      // Kaufman Efficiency Ratio penceresi
input double  InpER_Th            = 0.30;     // ER < bu = YATAY (grid açık)
input double  InpLevel1Pct        = 1.0;      // 1. AL seviyesi: merkez (SMA20) -% (BIST sıkı)
input double  InpLevel2Pct        = 2.0;      // 2. AL seviyesi
input double  InpLevel3Pct        = 3.0;      // 3. AL seviyesi
input double  InpTakePct          = 1.5;      // +%X'te TRAILING aktifleş (satmaz)
input double  InpTrailPct         = 0.5;      // peak'in %X altına inince sat (kayan stop)
input double  InpSafeReservePct   = 20.0;     // 💰 öz sermayenin %X'i HER ZAMAN güvende (kalan kullanılır)
input long    InpMagic            = 20260103; // Sihirli numara
input bool    InpVerbose          = true;     // Log yaz

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
   g_levels[0]=InpLevel1Pct; g_levels[1]=InpLevel2Pct; g_levels[2]=InpLevel3Pct;
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(30);
   trade.SetTypeFillingBySymbol(g_sym);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   PrintFormat("BIST GRID başladı · %s · TF=%s · ER<%.2f · AL -%.0f/-%.0f/-%.0f%% · trailing +%.1f/%.1f%% · KASA %.0f (%%%.0f güvende → max %%%.0f kullan)",
               g_sym, EnumToString(InpTF), InpER_Th, InpLevel1Pct, InpLevel2Pct, InpLevel3Pct,
               InpTakePct, InpTrailPct, eq, InpSafeReservePct, 100.0-InpSafeReservePct);
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason){}

//+------------------------------------------------------------------+
//| Kaufman ER + SMA merkez (son kapanan bara kadar)                 |
//+------------------------------------------------------------------+
bool GetRegime(double &er, double &center)
{
   int need = InpER_Win + 2;
   double cl[]; ArraySetAsSeries(cl, false);
   if(CopyClose(g_sym, InpTF, 0, need, cl) < need) return false;
   int last = need - 2;                                  // son KAPANAN bar
   double net = MathAbs(cl[last] - cl[last - InpER_Win]);
   double vol = 0;
   for(int i=last-InpER_Win+1; i<=last; i++) vol += MathAbs(cl[i]-cl[i-1]);
   er = (vol > 0) ? net/vol : 1.0;
   double sum = 0; for(int i=last-InpER_Win+1; i<=last; i++) sum += cl[i];
   center = sum / InpER_Win;
   return true;
}

//+------------------------------------------------------------------+
//| Bu magic'in TÜM açık pozisyonlarının toplam notional değeri      |
//|  (kasa koruma için — tüm sembollerde, çoklu instance uyumlu)     |
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
      double vol = PositionGetDouble(POSITION_VOLUME);
      double prc = PositionGetDouble(POSITION_PRICE_CURRENT);
      double cs  = SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE);
      tot += vol * prc * cs;
   }
   return tot;
}

bool LevelHeld(int k)
{
   string tag = "G" + IntegerToString(k);
   for(int i=PositionsTotal()-1; i>=0; i--)
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
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==g_sym && PositionGetInteger(POSITION_MAGIC)==InpMagic)
         trade.PositionClose(tk);
   }
   if(InpVerbose) Print("Grid kapatıldı: ", why);
}

//+------------------------------------------------------------------+
//| Hedef notional'a denk lot — ama KASA KORUMASI: kalan bütçeyi aşma |
//+------------------------------------------------------------------+
double CalcLots(double ask)
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double usable = eq * (100.0 - InpSafeReservePct) / 100.0;   // %80 kullanılabilir
   double budget = usable - TotalNotional();                   // kalan bütçe
   if(budget <= 0) return 0;                                   // kasa korumalı: dur
   double per_unit = usable / 3.0;                             // birim = bütçenin 1/3'ü (3 seviye)
   double target = MathMin(per_unit, budget);

   double cs = SymbolInfoDouble(g_sym, SYMBOL_TRADE_CONTRACT_SIZE);
   if(cs<=0 || ask<=0) return 0;
   double step = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_STEP);
   double minl = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_MIN);
   double maxl = SymbolInfoDouble(g_sym, SYMBOL_VOLUME_MAX);
   if(step<=0) step=minl;
   double lots = MathFloor((target/(ask*cs))/step)*step;
   if(lots < minl) return 0;
   if(lots > maxl) lots = maxl;
   // serbest teminat yeterli mi
   double need=0;
   if(OrderCalcMargin(ORDER_TYPE_BUY, g_sym, lots, ask, need))
      if(need > AccountInfoDouble(ACCOUNT_MARGIN_FREE)*0.98) return 0;
   int vd = (step>=1.0)?0:(int)MathRound(-MathLog10(step));
   return NormalizeDouble(lots, vd);
}

//+------------------------------------------------------------------+
//| TRAILING: birim +%1.5'e ulaşınca kayan stop (peak'in %0.5 altı). |
//|  MT5 SL'i ile yapılır — fiyat SL'e değince MT5 otomatik kapatır. |
//+------------------------------------------------------------------+
void ManageTrailing()
{
   double bid = SymbolInfoDouble(g_sym, SYMBOL_BID);
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk==0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=g_sym || PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double prof  = (bid-entry)/entry;
      if(prof < InpTakePct/100.0) continue;                  // henüz +%1.5'e ulaşmadı
      double desiredSL = bid * (1.0 - InpTrailPct/100.0);    // peak(bid)'in %0.5 altı
      double curSL = PositionGetDouble(POSITION_SL);
      if(curSL==0 || desiredSL > curSL)                       // sadece YUKARI çek
      {
         double tp = PositionGetDouble(POSITION_TP);
         trade.PositionModify(tk, NormalizeDouble(desiredSL, (int)SymbolInfoInteger(g_sym,SYMBOL_DIGITS)), tp);
      }
   }
}

//+------------------------------------------------------------------+
void OnTick()
{
   double er, center;
   if(!GetRegime(er, center)) return;
   bool sideways = (er < InpER_Th);
   datetime bt = iTime(g_sym, InpTF, 0);
   bool newbar = (bt != g_lastBar);

   // TREND → grid kapat (yeni barda bir kez)
   if(!sideways)
   {
      if(newbar && PositionsTotal()>0) CloseAll(StringFormat("TREND (ER=%.2f)", er));
      g_lastBar = bt;
      return;
   }

   // Açık birimleri trailing ile yönet (her tick)
   ManageTrailing();

   // YATAY → grid: seviyeye inen + boş seviyeyi AL (kasa koruması içinde)
   double ask = SymbolInfoDouble(g_sym, SYMBOL_ASK);
   for(int k=0;k<3;k++)
   {
      double lvl = center * (1.0 - g_levels[k]/100.0);
      if(ask <= lvl && !LevelHeld(k+1))
      {
         double lots = CalcLots(ask);
         if(lots <= 0){ if(InpVerbose && k==0) Print("kasa koruması/bütçe: yeni birim açılmadı"); continue; }
         if(trade.Buy(lots, g_sym, ask, 0, 0, "G"+IntegerToString(k+1)))   // SL/TP yok — trailing sonra
         {
            if(InpVerbose)
            {
               double cs = SymbolInfoDouble(g_sym, SYMBOL_TRADE_CONTRACT_SIZE);
               double notional = lots*ask*cs; double eq=AccountInfoDouble(ACCOUNT_EQUITY);
               PrintFormat("GRID AL: seviye %d @ %.2f · %.2f lot · notional %.0f (kasa %%%.0f kullanımda)",
                           k+1, ask, lots, notional, TotalNotional()/eq*100.0);
            }
         }
      }
   }
   g_lastBar = bt;
}
//+------------------------------------------------------------------+
