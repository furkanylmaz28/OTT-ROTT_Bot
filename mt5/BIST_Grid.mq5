//+------------------------------------------------------------------+
//|                                              BIST_Grid.mq5        |
//|  KANITLANMIŞ BIST GRID + TREND — her rejimde aktif, long-only     |
//|  YATAY (ER<0.25)→grid · YUKARI TREND→long · AŞAĞI TREND→nakit      |
//|  ÇOKLU SEMBOL: tüm Market Watch'ı tarar (InpScanAll).             |
//|  WF-opt param: seviye -1.5/-3/-4.5% · +%1.0 net'te trailing aktif,|
//|  grid peak'in %0.3 / trend %3 altına inince PİYASADAN kapat       |
//|  (broker SL YOK — bu hesapta desteklenmiyor; EA-hafızalı peak).   |
//|  💰 KASA KORUMA: öz sermayenin %20'si HER ZAMAN güvende (GLOBAL) —|
//|     tüm sembollerdeki toplam notional ≤ %80. Kaldıraç YOK. DEMO.  |
//+------------------------------------------------------------------+
#property copyright "OTT Bot — QUANT DESK"
#property version   "4.00"
#property strict
#include <Trade/Trade.mqh>

//============================ GİRDİLER ==============================
input bool    InpScanAll          = true;     // TÜM Market Watch sembollerini tara
input string  InpSymbols          = "GARAN,THYAO,ASELS,EREGL,SISE,KCHOL,AKBNK,SASA,TUPRS,FROTO"; // ScanAll=false ise
input ENUM_TIMEFRAMES InpTF        = PERIOD_H1; // Zaman dilimi (sistem H1)
input int     InpER_Win           = 20;      // Kaufman ER penceresi
input double  InpER_Th            = 0.25;     // ER < bu = YATAY (WF-opt: 0.30 en iyi DEĞİLDİ — holdout/OOS'ta 0.25 daha güçlü)
input double  InpLevel1Pct        = 1.5;      // 1. AL seviyesi: SMA20 -% (WF-opt: geniş daha iyi)
input double  InpLevel2Pct        = 3.0;      // 2. AL seviyesi (WF-opt -1.5/-3/-4.5)
input double  InpLevel3Pct        = 4.5;      // 3. AL seviyesi
input double  InpTakePct          = 1.0;      // +%X'te TRAILING aktifleş (WF-opt: 1.0 erken kilit)
input double  InpTrailPct         = 0.3;      // GRID: peak'in %X altına inince sat (WF-opt: 0.3 sıkı, az geri ver)
input double  InpTrendTrailPct    = 3.0;      // TREND-LONG: peak'in %X altı (GENİŞ → kazananı koştur, sabit TP yok)
input double  InpCommPct          = 0.10;     // Gidiş-dönüş komisyon % — trailing eşiğine eklenir (net kâr korunur)
input double  InpUnitPct          = 15.0;     // Birim başı = kasanın %X'i ile alabileceği kadar (demo: daha çok deployment için 10→15)
input bool    InpTrendLong        = true;     // TREND'de boş durma: yukarı trend (fiyat>SMA) → long tut
input bool    InpAllowShort       = false;    // SHORT (demo): tepeden sat grid + aşağı trend short (BIST drift'i aleyhe — PF düşer)
input double  InpSafeReservePct   = 10.0;     // 💰 %X HER ZAMAN güvende (GLOBAL) → toplam ≤ %90 (demo: 20→10 daha çok deployment)
input long    InpMagic            = 20260103;
input int     InpTimerSec         = 10;       // Tarama aralığı (sn)
input bool    InpVerbose          = true;

//============================ GLOBAL ===============================
CTrade    trade;
string    g_symbols[];
datetime  g_lastBar[];
double    g_levels[3];

// ── Peak takibi (EA hafızasında) — broker SL/TP (PositionModify) bu hesapta
// HER ZAMAN ret=10035 "invalid order" ile reddediyor (VIOP'ta native stop
// desteklenmiyor olabilir; tick-hizalama denendi, o da çözmedi). Bu yüzden
// trailing artık broker'a stop koymuyor — EA kendi hafızasında tepe/dip fiyatı
// tutup eşik aşılınca DOĞRUDAN piyasadan kapatıyor (PositionClose zaten
// çalışıyor — CloseTag'de kanıtlı). Backtest'in "peak/active" mantığıyla birebir.
ulong  g_pkTk[];
double g_pkVal[];

int PeakIdx(ulong tk){ for(int i=0;i<ArraySize(g_pkTk);i++) if(g_pkTk[i]==tk) return i; return -1; }
double PeakGet(ulong tk, double def){ int i=PeakIdx(tk); return (i>=0)?g_pkVal[i]:def; }
void PeakSet(ulong tk, double val)
{
   int i=PeakIdx(tk);
   if(i>=0){ g_pkVal[i]=val; return; }
   int n=ArraySize(g_pkTk); ArrayResize(g_pkTk,n+1); ArrayResize(g_pkVal,n+1);
   g_pkTk[n]=tk; g_pkVal[n]=val;
}
void PeakClear(ulong tk)
{
   int i=PeakIdx(tk); if(i<0) return;
   int n=ArraySize(g_pkTk);
   g_pkTk[i]=g_pkTk[n-1]; g_pkVal[i]=g_pkVal[n-1];
   ArrayResize(g_pkTk,n-1); ArrayResize(g_pkVal,n-1);
}

//+------------------------------------------------------------------+
int OnInit()
{
   int n = 0;
   if(InpScanAll)
   {
      // Önce sunucudaki TÜM F_ (VIOP tek-hisse futures) sembollerini Market Watch'a
      // ekle — taze kurulumda (bulut/VPS) Market Watch varsayılanlarında VIOP yoktur;
      // bu olmadan EA taze terminalde hiçbir BIST sembolü göremezdi.
      int all = SymbolsTotal(false), eklenen = 0;
      for(int i=0;i<all;i++)
      {
         string nm = SymbolName(i, false);
         if(StringFind(nm, "F_") == 0)
            if(SymbolSelect(nm, true)) eklenen++;
      }
      if(eklenen > 0) PrintFormat("Market Watch'a %d VIOP (F_) sembolü eklendi", eklenen);
      // Tarama listesi = Market Watch'taki SADECE F_ semboller. Taze terminalde
      // Market Watch varsayılanları forex/altın CFD'leri içerir — onlar bu sistemle
      // DOĞRULANMADI, EA kesinlikle taramamalı/işlem açmamalı.
      int tot = SymbolsTotal(true);
      ArrayResize(g_symbols, tot);
      for(int i=0;i<tot;i++)
      {
         string nm = SymbolName(i, true);
         if(StringFind(nm, "F_") == 0) g_symbols[n++] = nm;
      }
      ArrayResize(g_symbols, n);
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

bool LevelHeld(string sym, string prefix, int k)
{
   string tag = prefix + IntegerToString(k);
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==sym &&
         PositionGetInteger(POSITION_MAGIC)==InpMagic &&
         PositionGetString(POSITION_COMMENT)==tag) return true;
   }
   return false;
}

// Yorum öneki: "G" = grid birimi, "T" = trend-long
bool HasTag(string sym, string prefix)
{
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==sym && PositionGetInteger(POSITION_MAGIC)==InpMagic)
         if(StringFind(PositionGetString(POSITION_COMMENT), prefix)==0) return true;
   }
   return false;
}

// Sembolün DAYANAĞINI (underlying hisse) çıkar.
// VIOP futures: F_ALARK0626 → ALARK · nakit: ALARK.E → ALARK · sondaki vade (MMYY) atılır.
string Underlying(string s)
{
   int dot = StringFind(s, ".");
   if(dot > 0) s = StringSubstr(s, 0, dot);            // ALARK.E → ALARK
   if(StringFind(s, "F_") == 0) s = StringSubstr(s, 2); // F_ALARK0626 → ALARK0626
   int len = StringLen(s);
   while(len > 0)                                       // sondaki rakamları (vade) at
   {
      ushort ch = StringGetCharacter(s, len-1);
      if(ch >= '0' && ch <= '9') len--; else break;
   }
   return StringSubstr(s, 0, len);
}

// Aynı dayanağı BAŞKA bir kontrat/sembol zaten tutuyor mu? (çift maruziyet kapısı)
// F_ALARK0626 açıkken F_ALARK0726'ya yeni giriş = aynı ALARK'a iki kat → ENGELLE.
// Aynı sembolün kendi grid kademeleri sayılmaz (LevelHeld onları yönetir).
bool UnderlyingElsewhere(string sym)
{
   string u = Underlying(sym);
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk==0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      string ps = PositionGetString(POSITION_SYMBOL);
      if(ps!=sym && Underlying(ps)==u) return true;
   }
   return false;
}

void CloseTag(string sym, string prefix, string why)
{
   int closed=0;
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==sym && PositionGetInteger(POSITION_MAGIC)==InpMagic)
         if(StringFind(PositionGetString(POSITION_COMMENT), prefix)==0)
            { if(trade.PositionClose(tk)) { closed++; PeakClear(tk); } }
   }
   if(InpVerbose && closed>0) PrintFormat("Kapatıldı (%s %s): %d · %s", sym, prefix, closed, why);
}

// Fiyatı sembolün GERÇEK tick adımına yuvarla (ondalık basamak≠tick adımı olabilir,
// VIOP'ta yaygın: NormalizeDouble sadece basamak keser, adıma hizalamaz →
// broker "invalid order" (ret=10035) ile reddeder. Bu, TRALT/ODAS/OYAKC vakasının sebebiydi.
double NormalizeToTick(string sym, double price)
{
   double tick = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   if(tick <= 0) tick = SymbolInfoDouble(sym, SYMBOL_POINT);
   if(tick <= 0) return price;
   double rounded = MathRound(price / tick) * tick;
   int dg = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   return NormalizeDouble(rounded, dg);
}

//+------------------------------------------------------------------+
double CalcLots(string sym, double ask)
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double usable = eq * (100.0 - InpSafeReservePct) / 100.0;     // %80 GLOBAL
   double budget = usable - TotalNotional();                     // kalan global bütçe
   if(budget <= 0) return 0;                                     // kasa korumalı: dur
   double target = MathMin(eq * InpUnitPct/100.0, budget);       // birim = InpUnitPct% eq (vars. %10), bütçeyle sınırlı
   double cs = SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE);
   if(cs<=0 || ask<=0) return 0;
   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double minl = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double maxl = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   if(step<=0) step=minl;
   double lots = MathFloor((target/(ask*cs))/step)*step;
   if(lots < minl) return 0;   // %10 bütçe 1 kontrata yetmiyor (pahalı hisse) → ATLA (konsantre olma)
   if(lots > maxl) lots = maxl;
   double need=0;
   if(OrderCalcMargin(ORDER_TYPE_BUY, sym, lots, ask, need))
      if(need > AccountInfoDouble(ACCOUNT_MARGIN_FREE)*0.98) return 0;
   int vd = (step>=1.0)?0:(int)MathRound(-MathLog10(step));
   return NormalizeDouble(lots, vd);
}

//+------------------------------------------------------------------+
// GRID trailing: broker'a SL KOYMUYOR (bu hesapta PositionModify hep reddediliyor —
// ret=10035/10027, sembol/genişlikten bağımsız → VIOP'ta native stop desteklenmiyor
// olabilir). EA kendi hafızasında tepe fiyatı takip edip eşik aşılınca DOĞRUDAN
// piyasadan kapatır (PositionClose kanıtlı çalışıyor — CloseTag'de görüldü).
void TrailSym(string sym)
{
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   if(bid<=0) return;   // feed sıçraması/veri yok → dokunma (bid=0 iken kapatma tetiklenirdi!)
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk==0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=sym || PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      if(StringFind(PositionGetString(POSITION_COMMENT),"G")!=0) continue;  // sadece GRID birimleri trail
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      bool active = (PeakIdx(tk) >= 0);
      if(!active)
      {
         if((bid-entry)/entry < (InpTakePct+InpCommPct)/100.0) continue;  // +%1.1 NET (komisyon dahil) — henüz eşik yok
         PeakSet(tk, bid); active = true;                                 // AKTİFLEŞTİ
         if(InpVerbose) PrintFormat("✅ TRAILING AKTİF (grid): %s #%s giriş=%.4g tepe=%.4g", sym, (string)tk, entry, bid);
      }
      double peak = MathMax(PeakGet(tk, bid), bid);
      PeakSet(tk, peak);
      if(bid <= peak*(1.0 - InpTrailPct/100.0))
      {
         if(trade.PositionClose(tk))
         { PeakClear(tk); if(InpVerbose) PrintFormat("💰 TRAIL KAPANDI (grid): %s #%s tepe=%.4g @%.4g", sym, (string)tk, peak, bid); }
         else PrintFormat("❌ TRAIL KAPAT HATA (grid): %s #%s · ret=%d %s", sym, (string)tk, trade.ResultRetcode(), trade.ResultRetcodeDescription());
      }
   }
}

// SHORT grid trailing: kâr +%X'e ulaşınca dip fiyatı takip et, geri toparlanınca kapat
void TrailShort(string sym)
{
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   if(ask<=0) return;   // feed sıçraması/veri yok → dokunma
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk==0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=sym || PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      if(StringFind(PositionGetString(POSITION_COMMENT),"S")!=0) continue;  // sadece SHORT grid
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      bool active = (PeakIdx(tk) >= 0);
      if(!active)
      {
         if((entry-ask)/entry < (InpTakePct+InpCommPct)/100.0) continue;  // +%1.1 NET (komisyon dahil) — diğer 3 fonksiyonla tutarlı
         PeakSet(tk, ask); active = true;
         if(InpVerbose) PrintFormat("✅ TRAILING AKTİF (short): %s #%s giriş=%.4g dip=%.4g", sym, (string)tk, entry, ask);
      }
      double trough = MathMin(PeakGet(tk, ask), ask);
      PeakSet(tk, trough);
      if(ask >= trough*(1.0 + InpTrailPct/100.0))
      {
         if(trade.PositionClose(tk))
         { PeakClear(tk); if(InpVerbose) PrintFormat("💰 TRAIL KAPANDI (short): %s #%s dip=%.4g @%.4g", sym, (string)tk, trough, ask); }
         else PrintFormat("❌ TRAIL KAPAT HATA (short): %s #%s · ret=%d %s", sym, (string)tk, trade.ResultRetcode(), trade.ResultRetcodeDescription());
      }
   }
}

// TREND-LONG trailing: kâr +%1.1 net olunca GENİŞ trail (peak'in %3 altı) → kazananı koştur, sabit TP yok
void TrailTrend(string sym)
{
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   if(bid<=0) return;   // feed sıçraması/veri yok → dokunma (bid=0 iken kapatma tetiklenirdi!)
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk==0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=sym || PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      if(PositionGetString(POSITION_COMMENT)!="T") continue;       // sadece trend-long
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      bool active = (PeakIdx(tk) >= 0);
      if(!active)
      {
         if((bid-entry)/entry < (InpTakePct+InpCommPct)/100.0) continue;  // +%1.1 net olmadan aktifleşmez
         PeakSet(tk, bid); active = true;
         if(InpVerbose) PrintFormat("✅ TRAILING AKTİF (trend): %s #%s giriş=%.4g tepe=%.4g", sym, (string)tk, entry, bid);
      }
      double peak = MathMax(PeakGet(tk, bid), bid);
      PeakSet(tk, peak);
      if(bid <= peak*(1.0 - InpTrendTrailPct/100.0))
      {
         if(trade.PositionClose(tk))
         { PeakClear(tk); if(InpVerbose) PrintFormat("💰 TRAIL KAPANDI (trend): %s #%s tepe=%.4g @%.4g", sym, (string)tk, peak, bid); }
         else PrintFormat("❌ TRAIL KAPAT HATA (trend): %s #%s giriş=%.4g bid=%.4g peak=%.4g · ret=%d %s",
                           sym, (string)tk, entry, bid, peak, trade.ResultRetcode(), trade.ResultRetcodeDescription());
      }
   }
}

// TREND-SHORT trailing: kâr net olunca GENİŞ trail (peak'in %3 üstü) → kazananı koştur, sabit TP yok
// TrailTrend'in ("T") ayna simetriği — bu olmadan "D" pozisyonları hiç korumasız kalırdı.
void TrailTrendShort(string sym)
{
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   if(ask<=0) return;
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk==0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=sym || PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      if(PositionGetString(POSITION_COMMENT)!="D") continue;       // sadece trend-short
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      bool active = (PeakIdx(tk) >= 0);
      if(!active)
      {
         if((entry-ask)/entry < (InpTakePct+InpCommPct)/100.0) continue;  // +%1.1 net olmadan aktifleşmez
         PeakSet(tk, ask); active = true;
         if(InpVerbose) PrintFormat("✅ TRAILING AKTİF (trend-short): %s #%s giriş=%.4g dip=%.4g", sym, (string)tk, entry, ask);
      }
      double trough = MathMin(PeakGet(tk, ask), ask);
      PeakSet(tk, trough);
      if(ask >= trough*(1.0 + InpTrendTrailPct/100.0))
      {
         if(trade.PositionClose(tk))
         { PeakClear(tk); if(InpVerbose) PrintFormat("💰 TRAIL KAPANDI (trend-short): %s #%s dip=%.4g @%.4g", sym, (string)tk, trough, ask); }
         else PrintFormat("❌ TRAIL KAPAT HATA (trend-short): %s #%s · ret=%d %s", sym, (string)tk, trade.ResultRetcode(), trade.ResultRetcodeDescription());
      }
   }
}

//+------------------------------------------------------------------+
void OnTimer()
{
   int n = ArraySize(g_symbols);
   int nSide=0, nUp=0, nDown=0, nUpAfford=0, nSideAfford=0, nSideDip=0, nData=0;  // tanı sayaçları
   for(int s=0; s<n; s++)
   {
      string sym = g_symbols[s];
      trade.SetTypeFillingBySymbol(sym);     // HER sembol için doğru emir-doldurma (yoksa emir reddedilir!)
      double er, center;
      if(!GetRegime(sym, er, center)) continue;
      nData++;
      bool sideways = (er < InpER_Th);
      datetime bt = iTime(sym, InpTF, 0);
      if(bt==0) continue;
      bool newbar = (bt != g_lastBar[s]);
      double bid = SymbolInfoDouble(sym, SYMBOL_BID);
      double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
      // ── TRAILING her taramada, REJİMDEN BAĞIMSIZ çalışır. Eskiden rejim
      //    dallarının içindeydi → ER bar ortasında yatay→trend geçince grid
      //    pozisyonları yeni bara kadar (59 dk'ya kadar) İZLENMİYORDU; broker
      //    SL de olmadığından tamamen korumasız pencere oluşuyordu.
      TrailSym(sym); TrailShort(sym); TrailTrend(sym); TrailTrendShort(sym);
      // ── tanı: rejim + bütçe uygunluğu say
      {
         double eq0=AccountInfoDouble(ACCOUNT_EQUITY);
         double cs0=SymbolInfoDouble(sym,SYMBOL_TRADE_CONTRACT_SIZE);
         double ml0=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
         bool afford=(ask>0 && cs0>0 && ml0*ask*cs0 <= eq0*InpUnitPct/100.0);
         if(sideways)
         {
            nSide++;
            if(afford) nSideAfford++;
            if(afford && ask <= center*(1.0-g_levels[0]/100.0)) nSideDip++;  // uygun + ilk seviyede (dip)
         }
         else if(bid>center){ nUp++; if(afford) nUpAfford++; }
         else nDown++;
      }

      // ════════ TREND (ER ≥ eşik) ════════
      if(!sideways)
      {
         if(newbar)
         {
            if(HasTag(sym,"G")) CloseTag(sym,"G", StringFormat("TREND (ER=%.2f)", er));  // long grid kapat
            if(HasTag(sym,"S")) CloseTag(sym,"S", StringFormat("TREND (ER=%.2f)", er));  // short grid kapat
            bool up = (bid > center);                             // yön: fiyat>SMA = yukarı
            // YUKARI trend → trend-long
            if(InpTrendLong && ask>0 && up && !HasTag(sym,"T") && !UnderlyingElsewhere(sym))
            {
               double lots = CalcLots(sym, ask);
               if(lots>0 && trade.Buy(lots, sym, ask, 0, 0, "T"))
                  if(InpVerbose) PrintFormat("TREND-LONG AL: %s @ %.4g · %.2f lot (ER=%.2f yukarı)", sym, ask, lots, er);
            }
            if(up && HasTag(sym,"D")) CloseTag(sym,"D","yukarı döndü");   // short kapat
            // AŞAĞI trend → trend-short (sadece demo/AllowShort)
            if(InpAllowShort && bid>0 && !up && !HasTag(sym,"D") && !UnderlyingElsewhere(sym))
            {
               double lots = CalcLots(sym, bid);
               if(lots>0 && trade.Sell(lots, sym, bid, 0, 0, "D"))
                  if(InpVerbose) PrintFormat("TREND-SHORT SAT: %s @ %.4g · %.2f lot (ER=%.2f aşağı)", sym, bid, lots, er);
            }
            if(!up && HasTag(sym,"T")) CloseTag(sym,"T","aşağı trend"); // long kapat
            if(!InpTrendLong && HasTag(sym,"T")) CloseTag(sym,"T","trend-long kapalı");
            if(!InpAllowShort && HasTag(sym,"D")) CloseTag(sym,"D","short kapalı");
         }
         g_lastBar[s] = bt;
         continue;
      }

      // ════════ YATAY (ER < eşik) → GRID ════════
      if(HasTag(sym,"T")) CloseTag(sym,"T","yataya döndü");       // trend bitti → trend pozisyonları kapat
      if(HasTag(sym,"D")) CloseTag(sym,"D","yataya döndü");
      if(ask<=0){ g_lastBar[s]=bt; continue; }
      for(int k=0;k<3;k++)
      {
         // LONG grid: merkez altı seviyeye inince al
         double lvlL = center * (1.0 - g_levels[k]/100.0);
         if(ask <= lvlL && !LevelHeld(sym, "G", k+1) && !UnderlyingElsewhere(sym))
         {
            double lots = CalcLots(sym, ask);
            if(lots > 0)
            {
               if(trade.Buy(lots, sym, ask, 0, 0, "G"+IntegerToString(k+1)))
               { double eq=AccountInfoDouble(ACCOUNT_EQUITY);
                 PrintFormat("✅ GRID AL: %s sev%d @ %.4g · %.2f lot · kasa %%%.0f", sym, k+1, ask, lots, TotalNotional()/eq*100.0); }
               else
                 PrintFormat("❌ GRID AL HATA: %s · %.2f lot · ret=%d %s", sym, lots, trade.ResultRetcode(), trade.ResultRetcodeDescription());
            }
         }
         // SHORT grid: merkez üstü seviyeye çıkınca sat (demo/AllowShort)
         if(InpAllowShort)
         {
            double lvlS = center * (1.0 + g_levels[k]/100.0);
            if(bid >= lvlS && !LevelHeld(sym, "S", k+1) && !UnderlyingElsewhere(sym))
            {
               double lots = CalcLots(sym, bid);
               if(lots > 0 && trade.Sell(lots, sym, bid, 0, 0, "S"+IntegerToString(k+1)))
                  if(InpVerbose) PrintFormat("GRID SAT (short): %s sev%d @ %.4g · %.2f lot", sym, k+1, bid, lots);
            }
         }
      }
      g_lastBar[s] = bt;
      Sleep(5);
   }
   // ── TANI ÖZETİ (30 sn'de bir) — neden işlem açıldı/açılmadı
   static datetime lastDiag = 0;
   if(TimeCurrent() - lastDiag >= 30)
   {
      lastDiag = TimeCurrent();
      double eq=AccountInfoDouble(ACCOUNT_EQUITY);
      PrintFormat("TANI: veri %d · 🟦yatay %d (uygun %d, DİP'te %d) · 📈yukarı %d (uygun %d) · 📉aşağı %d · açık %d · kasa %%%.0f",
                  nData, nSide, nSideAfford, nSideDip, nUp, nUpAfford, nDown, PositionsTotal(), TotalNotional()/eq*100.0);
      if(nSideDip==0 && nUpAfford==0)
         Print("→ İşlem yok: uygun-fiyatlı + dip'teki yatay hisse yok, uygun yukarı-trend yok. (Bütçe uygun azsa → birim %% artır ya da ucuz hisse)");
   }
}
//+------------------------------------------------------------------+
