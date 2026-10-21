# Instrukcja obsługi tradescan

Przewodnik dla osób, które nie są programistami ani doświadczonymi traderami. Po jego przeczytaniu będziesz wiedzieć, **co robi każdy ekran i każde polecenie, po co zostało stworzone, jak go użyć na konkretnym przykładzie i co dzięki niemu zyskujesz**.

> **To nie jest porada inwestycyjna.** `tradescan` to narzędzie badawcze. Każda liczba, którą pokazuje, jest statystyką z przeszłości. Przeszłość nie gwarantuje przyszłości. Decyzje o pieniądzach podejmujesz sam i na własną odpowiedzialność.

> **O przykładach w tym dokumencie.** Wartości liczbowe w przykładach (zyski, tickery, wyniki) są **ilustracyjne**: pokazują, jak czytać ekran, a nie jakie wyniki dostaniesz. Prawdziwe wyniki zależą od danych z dnia, w którym uruchamiasz program. Nazwy pól i przycisków podaję tak, jak widać je w programie, po angielsku (np. `Pin run`), a wyjaśniam po polsku.

## Spis treści

1. [Czym jest tradescan i po co powstał](#1-czym-jest-tradescan-i-po-co-powstał)
2. [Słowniczek](#2-słowniczek)
3. [Instalacja i pierwsze uruchomienie](#3-instalacja-i-pierwsze-uruchomienie)
4. [Jak jest zbudowany interfejs](#4-jak-jest-zbudowany-interfejs)
5. [Ekrany programu](#5-ekrany-programu)
   - [Scanner](#51-scanner--co-warto-obejrzeć-dzisiaj)
   - [Backtest](#52-backtest--czy-ten-pomysł-działał-w-przeszłości)
   - [Sweep](#53-sweep--które-ustawienie-jest-najlepsze)
   - [Walk-forward](#54-walk-forward--bardziej-uczciwy-test-niż-sweep)
   - [Watchlist](#55-watchlist--ten-sam-pomysł-na-wielu-instrumentach)
   - [Portfolio](#56-portfolio--jedno-konto-wiele-pozycji)
   - [Rotation](#57-rotation--trzymaj-najsilniejszych)
   - [Edge](#58-edge--który-sygnał-miał-przewagę)
   - [Compare](#59-compare--porównanie-przypiętych-wyników)
   - [Journal](#510-journal--dziennik-prawdziwych-transakcji)
   - [Signals](#511-signals--biblioteka-sygnałów)
6. [Scenariusze krok po kroku](#6-scenariusze-krok-po-kroku)
7. [Biblioteka sygnałów (38)](#7-biblioteka-sygnałów-38)
8. [Reguły backtestu: filtry, wejścia, wyjścia, pyramiding](#8-reguły-backtestu-filtry-wejścia-wyjścia-pyramiding)
9. [Jak czytać wyniki i nie dać się oszukać](#9-jak-czytać-wyniki-i-nie-dać-się-oszukać)
10. [Konfiguracja: settings.toml i listy obserwowanych](#10-konfiguracja-settingstoml-i-listy-obserwowanych)
11. [Wiersz poleceń (CLI)](#11-wiersz-poleceń-cli)
12. [Dane, zapis i kopie zapasowe](#12-dane-zapis-i-kopie-zapasowe)
13. [Bezpieczeństwo](#13-bezpieczeństwo)
14. [Ograniczenia, o których musisz wiedzieć](#14-ograniczenia-o-których-musisz-wiedzieć)
15. [Najczęstsze pytania i problemy](#15-najczęstsze-pytania-i-problemy)
16. [Planowane i w przygotowaniu](#16-planowane-i-w-przygotowaniu)
17. [Dla programistów: jak rozszerzać program](#17-dla-programistów-jak-rozszerzać-program)

---

## 1. Czym jest tradescan i po co powstał

### Problem

Kto kiedykolwiek próbował inwestować lub handlować na giełdzie, zna sytuację: ktoś mówi „kup, gdy cena przebije 20-dniowe maksimum” albo „kupuj, gdy wskaźnik RSI spadnie poniżej 10”. Brzmi rozsądnie, ale **czy ta reguła naprawdę działała**? I czy działała dlatego, że jest dobra, czy dlatego, że akurat trafiła na dobry okres?

Odpowiedzi na takie pytania da się sprawdzić na danych historycznych, ale ręcznie jest to żmudne i łatwo o błędy: podglądanie przyszłości, pominięcie kosztów, wybranie wyniku, który „ładnie wygląda”.

### Rozwiązanie

`tradescan` robi trzy rzeczy:

1. **Skanuje rynek.** Codziennie sprawdza listę instrumentów (akcje, ETF-y, krypto) pod kątem 38 gotowych sygnałów i pokazuje te, na których coś się właśnie wydarzyło, uszeregowane od najciekawszych. Do każdego daje gotowy plan ryzyka: gdzie postawić stop, gdzie cele, ile kupić.
2. **Testuje pomysły na przeszłości (backtest).** Bierze regułę, np. „kup po sygnale `donchian_breakout`, wyjdź na stopie, celu lub po 20 dniach”, i odtwarza, co by się stało na ostatnich latach danych, z prowizjami i poślizgiem cenowym.
3. **Sprawdza, czy wynik jest wiarygodny.** Dzieli historię na część „do uczenia” i część „do sprawdzenia”, losuje kolejność transakcji (Monte Carlo), przeprowadza testy typu walk-forward. Pokazuje, czy dobry wynik to coś więcej niż szczęście.

Do tego dochodzą: dziennik prawdziwych transakcji (porównasz swoje wyniki z backtestem, który je podpowiedział) i porównywarka zapisanych wyników.

### Co Ci to daje

- **Oszczędność czasu:** zamiast przeglądać setki wykresów, widzisz posortowaną listę kandydatów.
- **Dyscyplina:** każda propozycja ma stop, cele i wielkość pozycji liczoną z ryzyka, które sam ustawiasz (np. 1% konta).
- **Uczciwa weryfikacja:** program jest zbudowany tak, by utrudniać samooszukiwanie się (patrz [rozdział 9](#9-jak-czytać-wyniki-i-nie-dać-się-oszukać)).
- **Powtarzalność:** ten sam test daje ten sam wynik, a zapisane wyniki możesz zestawić obok siebie.
- **Wszystko jest regulowane:** każdy parametr strategii można zmienić w przeglądarce i od razu zobaczyć, co to zmieniło.

### Czego tradescan **nie** robi

- Nie składa zleceń w żadnym domu maklerskim. Niczego nie kupuje ani nie sprzedaje.
- Nie przewiduje przyszłości. Pokazuje, jak podobne sytuacje wyglądały w przeszłości.
- Nie obsługuje danych śróddziennych w testach: pracuje na **dziennych** świecach.
- Nie ma logowania ani kont użytkowników. To program lokalny, dla jednej osoby na jednym komputerze.

### Jak to działa w skrócie

Dane (ceny dzienne) pobierane są z Yahoo Finance przez bibliotekę `yfinance` i zapamiętywane na dysku. Sygnały liczone są szybko w bibliotece `pandas` („silnik vectorized”). Opcjonalnie ten sam test może być uruchomiony w drugim, wolniejszym silniku, **Cerebro** (biblioteka `backtrader`), który odtwarza zlecenia „jak na prawdziwym rynku”. Oba silniki mają dawać **te same transakcje**; jeśli dają, to znak, że wyniki są wiarygodne i że nie ma błędu w jednym z nich.

---

## 2. Słowniczek

Poniższe pojęcia wracają w całym dokumencie. Wróć tu, gdy czegoś nie rozumiesz.

### Podstawy rynku

| Pojęcie | Znaczenie |
| --- | --- |
| **Ticker** | Skrót nazwy instrumentu na giełdzie, np. `AAPL` (Apple), `SPY` (ETF na indeks S&P 500), `PKO.WA` (PKO BP na GPW; końcówka `.WA` to Warszawa), `BTC-USD` (bitcoin). Spółki z klasami akcji zapisujesz z myślnikiem: `BRK-B`. |
| **Świeca (bar)** | Jeden dzień notowań: cena otwarcia, najwyższa, najniższa, zamknięcia i wolumen. Program pracuje na świecach dziennych. |
| **Wolumen** | Liczba sprzedanych akcji w danym dniu. Duży wolumen = duże zainteresowanie. |
| **Long / short** | Long: zarabiasz, gdy cena rośnie. Short: zarabiasz, gdy cena spada (sprzedajesz „na krótko”). |
| **ETF** | Fundusz notowany na giełdzie, który odwzorowuje indeks lub grupę aktywów. |
| **Benchmark** | Punkt odniesienia, z którym porównujesz wynik, zwykle indeks, np. `SPY`. |
| **Buy & hold** | Kup na początku, trzymaj do końca. Najprostsza strategia, z którą warto się porównywać: jeśli Twoja skomplikowana strategia nie bije buy & hold, to po co ją stosować? |
| **Trend** | Ogólny kierunek ceny. Rosnący trend: cena wyżej niż jej średnia z 200 dni. |
| **SMA / EMA** | Średnia krocząca (prosta / wykładnicza): średnia ceny z ostatnich N dni. Wygładza wykres i pokazuje trend. EMA bardziej waży najnowsze dni. |
| **RSI** | Wskaźnik „wykupienia/wyprzedania” od 0 do 100. Niska wartość (np. < 10): cena spadła szybko i mocno. Wysoka (np. > 90): wzrosła szybko i mocno. |
| **ATR** | Średni dzienny rozrzut ceny (od najniższej do najwyższej) z ostatnich N dni (domyślnie 14). To miara „jak mocno ten instrument się rusza”. Służy do ustawiania stopów dopasowanych do zmienności. |
| **ADX** | Siła trendu (nie jego kierunek). Powyżej ok. 20 trend jest wyraźny. |
| **Pasma Bollingera** | Pasmo wokół średniej, szerokie na 2 odchylenia standardowe. Cena poza pasmem to ruch nietypowo duży. |
| **Gap** | Luka: dzisiejsze otwarcie wyraźnie powyżej (lub poniżej) wczorajszego zamknięcia. |

### Zlecenia i zarządzanie ryzykiem

| Pojęcie | Znaczenie |
| --- | --- |
| **Stop (stop-loss)** | Cena, przy której zamykasz stratną pozycję, żeby strata nie rosła. W programie początkowy stop to `atr_mult` × ATR od ceny wejścia (domyślnie 2 × ATR). |
| **Cel (target)** | Cena, przy której zamykasz pozycję z zyskiem. |
| **R (R-multiple)** | Jednostka ryzyka. **1R = to, co ryzykujesz w jednej transakcji** (odległość od wejścia do stopu, razem z wielkością pozycji). Zysk 2R znaczy „zarobiłem dwa razy tyle, ile ryzykowałem”, strata −1R: „straciłem dokładnie tyle, ile zakładałem”. Dzięki R porównujesz transakcje na różnych instrumentach i kontach. |
| **Ryzyko na transakcję (`risk_pct`)** | Jaką część konta jesteś gotów stracić na jednej transakcji, domyślnie 1%. Wielkość pozycji wylicza się tak, żeby trafienie w stop kosztowało właśnie tyle. |
| **Pozycja maksymalna (`max_position_pct`)** | Górny limit wartości pozycji jako % konta (domyślnie 25%). Chroni przed zbyt dużą pozycją, gdy stop jest bardzo blisko. |
| **Zlecenie z limitem (limit)** | „Kup nie drożej niż X”. |
| **Zlecenie stop (buy-stop)** | „Kup, gdy cena dojdzie do X” (typowo: wejście na wybiciu). |
| **Prowizja i poślizg (commission, slippage)** | Koszty transakcji: prowizja domu maklerskiego i różnica między ceną oczekiwaną a faktyczną. Domyślnie 0,1% i 0,05%. Bez nich backtest zawsze wygląda lepiej niż rzeczywistość. |
| **Pyramiding** | Dokupowanie do wygrywającej pozycji w miarę jej wzrostu (styl „Żółwi”). |

### Wyniki i statystyki

| Pojęcie | Znaczenie |
| --- | --- |
| **Equity (kapitał)** | Wartość konta w czasie; wykres `equity` to krzywa Twojego konta w backtestcie. |
| **Total return** | Łączny zysk w % za cały okres. |
| **CAGR** | Średni roczny zysk (z procentem składanym). Pozwala porównywać okresy różnej długości. |
| **Drawdown (obsunięcie)** | Spadek konta od ostatniego szczytu. **Max drawdown** to najgłębsze takie obsunięcie, np. −25% znaczy, że w najgorszym momencie byłeś 25% poniżej swojego rekordu. To najlepsza miara „ile to może boleć”. |
| **Win rate** | Odsetek transakcji zakończonych zyskiem. Sam z siebie nic nie znaczy: 30% trafień przy zyskach 4R i stratach 1R jest świetne, a 80% trafień przy zyskach 0,2R i stratach 2R to katastrofa. |
| **Profit factor** | Suma zysków ÷ suma strat. Powyżej 1 strategia zarabia; 1,5–2 to solidny wynik. |
| **Expectancy (w R)** | Średni wynik jednej transakcji w R. Dodatnia = strategia ma „przewagę” (edge). To jedna z najważniejszych liczb. |
| **Sharpe / Sortino** | Zysk w stosunku do wahań konta (Sortino liczy tylko wahania w dół). Wyższe = bardziej „równy” zysk. Powyżej 1 uchodzi za dobre. |
| **SQN** | Miara jakości systemu: expectancy w R podzielona przez zmienność R, skalowana liczbą transakcji. Pomaga ocenić, czy przewaga jest istotna. |
| **Exposure** | Odsetek czasu, w którym byłeś w rynku. Niska ekspozycja i podobny zysk do buy & hold to zaleta. |
| **Edge** | „Przewaga”: o ile sygnał poprawia wynik względem losowego dnia. |

### Weryfikacja

| Pojęcie | Znaczenie |
| --- | --- |
| **In-sample (IS)** | Część historii, na której możesz „stroić” parametry. |
| **Out-of-sample (OOS)** | Część historii **ukryta** przed strojeniem (domyślnie ostatnie 30%). To egzamin. Wynik dobry w IS, a słaby w OOS to znak, że dopasowałeś strategię do przeszłości. |
| **Overfitting (dopasowanie do przeszłości)** | Strategia ustawiona tak, że świetnie pasuje do konkretnych danych historycznych i nie działa na nowych. Największy wróg testowania strategii. |
| **Survivorship bias** | Błąd przetrwania: lista dzisiejszych spółek z S&P 500 nie zawiera tych, które wypadły z indeksu, więc historyczne wyniki wyglądają lepiej niż były. |
| **Monte Carlo** | Wielokrotne losowe przetasowanie Twoich transakcji, żeby zobaczyć, jak głębokie obsunięcie i jak długą serię strat mogłeś mieć, gdyby kolejność była inna. |
| **Walk-forward** | Powtarzane „strojenie na kawałku historii, handel na następnym kawałku”. Najbliższe temu, co zrobiłbyś w prawdziwym życiu. |
| **Rotacja momentum** | Strategia trzymająca regularnie przestawiane „najsilniejsze” instrumenty z listy, bez sygnałów wejścia i stopów. |
| **Waga sygnału / score (wynik zbieżności)** | Punktacja scanera: im więcej niezależnych argumentów (sygnały, trend, siła względna) wskazuje w tę samą stronę, tym wyższy wynik. |
| **Siła względna (RS)** | Jak instrument radził sobie na tle reszty listy w ostatnich miesiącach. |

---

## 3. Instalacja i pierwsze uruchomienie

### Czego potrzebujesz

- **Windows** (instrukcja pokazuje polecenia dla Windows; na innych systemach zmieniają się tylko ścieżki).
- **Python 3.11 lub nowszy.**
- **Node.js** z npm, tylko po to, by zbudować interfejs w przeglądarce.
- Połączenie z internetem przy pierwszym pobieraniu danych.

### Krok 1: środowisko Pythona i instalacja

Otwórz terminal w folderze projektu i wpisz:

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[cerebro,api,dev]"
```

Co to robi: pierwsze polecenie tworzy odizolowane środowisko Pythona (`.venv`), drugie instaluje program wraz z dodatkami:

- `cerebro`: drugi silnik backtestów (`backtrader`). Opcjonalny; bez niego wszystko działa poza opcją `--engine cerebro`.
- `api`: serwer WWW (FastAPI, uvicorn). Potrzebny do interfejsu w przeglądarce.
- `dev`: narzędzia testowe. Zwykły użytkownik może je pominąć.

### Krok 2: zbudowanie interfejsu

```bash
npm --prefix frontend install
npm --prefix frontend run build
```

Pierwsze polecenie pobiera biblioteki interfejsu, drugie buduje gotową stronę. Robisz to jednorazowo (i po aktualizacji programu).

### Krok 3: start

```bash
tradescan serve
```

Otwórz w przeglądarce adres **http://127.0.0.1:8000**. Jeden serwer dostarcza i interfejs, i API (dokumentacja API pod `/docs`).

Zatrzymanie: `Ctrl+C` w terminalu.

**Ważne:** uruchamiaj polecenia **z folderu projektu**, żeby program znalazł `config/settings.toml` i `config/watchlists/` (albo podaj ich lokalizację przez `--config` i `--watchlists-dir`).

### Pierwszy test: czy działa?

1. Wejdź na ekran **Scanner**.
2. Wybierz listę (np. `etf`) i naciśnij **Scan**.
3. Pierwsze uruchomienie pobiera dane każdego instrumentu, więc zajmie chwilę (dla dużych list nawet 1–2 minuty). Kolejne korzystają z pamięci podręcznej i są szybkie.
4. Zobaczysz baner z oceną rynku i tabelę propozycji. Jeśli tak, wszystko działa.

### Inne opcje startu

| Polecenie | Co robi |
| --- | --- |
| `tradescan serve --port 9000` | Inny port, gdy 8000 jest zajęty. |
| `tradescan serve --db D:\dane\moje.db` | Inny plik bazy z zapisanymi wynikami i dziennikiem (domyślnie `tradescan.db` w folderze, z którego startujesz). |
| `tradescan serve --no-cache` | Zawsze pobieraj świeże dane. |

---

## 4. Jak jest zbudowany interfejs

### Menu główne

U góry znajdziesz zakładki: **Scanner**, **Backtest**, **Sweep**, **Walk-forward**, **Watchlist**, **Portfolio**, **Rotation**, **Edge**, **Compare**, **Journal**, **Signals**. Każda opisana jest w [rozdziale 5](#5-ekrany-programu).

### Kolejność, w jakiej zwykle się z nich korzysta

```
Scanner  ──► znajduję kandydata
Backtest ──► sprawdzam jego regułę na jednym instrumencie
Sweep / Walk-forward ──► sprawdzam, czy ustawienia są odporne
Watchlist / Portfolio ──► sprawdzam na wielu instrumentach
Compare ──► zestawiam kilka wersji
Journal ──► zapisuję prawdziwą transakcję i porównuję z backtestem
```

### Konto w nagłówku

W nagłówku jest menu konta (**Account size and risk per trade**). Ustawiasz tam:

- **wielkość konta** (`equity`, domyślnie 100 000),
- **ryzyko na transakcję** (`risk_pct`, domyślnie 1%),
- **maksymalną pozycję** (`max_position_pct`, domyślnie 25% konta),
- **wielkość kroku zlecenia** (`lot_size`, domyślnie 1; dla krypto np. 0,0001, bo kupuje się ułamki).

Te wartości zapamiętuje przeglądarka i używają ich plan ryzyka w Scannerze oraz wszystkie backtesty.

**Przykład:** konto 50 000 zł, ryzyko 1% → na jednej transakcji ryzykujesz 500 zł. Jeśli stop jest 2 zł pod ceną wejścia, program zaproponuje 250 akcji (250 × 2 zł = 500 zł), chyba że wartość pozycji przekroczyłaby 25% konta, wtedy obetnie ją do limitu.

### Motyw jasny / ciemny

Przycisk motywu w nagłówku przełącza kolory. Wykresy dopasowują się same.

### Formularze żyją w adresie URL

Wszystko, co ustawisz w formularzu (też zmienione parametry), zapisuje się w adresie strony. Dzięki temu:

- możesz dodać test do zakładek i wrócić do niego później,
- możesz wysłać link komuś, kto ma uruchomiony ten sam program,
- możesz otworzyć dwa warianty w dwóch kartach i porównać je wzrokiem.

### Podświetlanie zmian

Parametr, którego wartość różni się od domyślnej, jest **podświetlony**. Zakres dozwolonych wartości jest sprawdzany na bieżąco; wartość spoza zakresu zostanie odrzucona z komunikatem, a nie po cichu poprawiona.

### Zaawansowane ustawienia (Advanced settings)

Scanner i Edge mają panel **Advanced settings** z każdym pozostałym parametrem (wagi punktacji, okresy trendu, progi reżimu rynku itd.). Zwykle nie musisz go ruszać. Przyda się, gdy chcesz sprawdzić, jak wynik zależy od takiego ustawienia.

### Jeden wspólny zestaw pól

Ekrany Backtest, Sweep, Walk-forward, Watchlist i Portfolio mają **ten sam zestaw pól „setup”** (sygnał, filtry, wejście, wyjścia, koszty, konto). Zbudowany raz układ przenosisz między nimi linkiem; część ekranów ma przycisk otwierający wynik na stronie Backtest.

---

## 5. Ekrany programu

Każda sekcja ma ten sam układ: **po co jest ekran**, **jak go użyć**, **jak czytać wynik**, **przykład**, **co Ci to daje**.

### 5.1 Scanner — co warto obejrzeć dzisiaj

**Po co.** Sprawdza całą listę instrumentów (np. 500 spółek z S&P 500) i pokazuje te, na których w ostatnich dniach pojawił się jakiś sygnał, uszeregowane od najmocniejszych argumentów. Zastępuje ręczne przeglądanie setek wykresów.

**Jak użyć.**

1. Wybierz **listę** (watchlist) albo wpisz własne tickery.
2. Opcjonalnie zawęź: kierunek (long / short / oba), rodziny sygnałów, minimalny wynik, jak świeży ma być sygnał (`fresh`, domyślnie 3 ostatnie świece).
3. Naciśnij **Scan**.

**Baner „reżimu rynku”.** Nad tabelą zobaczysz jedną z trzech ocen: *risk-on*, *neutral*, *risk-off*. Powstaje z trzech rzeczy: czy indeks odniesienia (benchmark) jest powyżej swojej średniej z 200 dni, jaki procent listy jest powyżej średniej z 50 dni (szerokość rynku) oraz ile instrumentów robi nowe 52-tygodniowe maksima i minima.

- *risk-on*: benchmark nad średnią 200 dni i szerokość ≥ 60%. Sprzyja pozycjom long.
- *risk-off*: benchmark pod średnią 200 dni i szerokość ≤ 40%. Sprzyja ostrożności lub short.
- *neutral*: wszystko pomiędzy.

**Tabela propozycji (kolumny).**

| Kolumna | Co znaczy |
| --- | --- |
| `Ticker` | Instrument. |
| `Dir` | Kierunek propozycji: long czy short. |
| `Score` | **Wynik zbieżności.** Suma wag świeżych sygnałów + premie za zgodny trend dzienny, trend tygodniowy i siłę względną (patrz niżej). Im wyżej, tym więcej argumentów w tę samą stronę. |
| `Signals (bars ago)` | Które sygnały zadziałały i ile świec temu. |
| `Close`, `Chg` | Ostatnie zamknięcie i dzienna zmiana. |
| `Trend` | Zgodność z trendem dziennym i tygodniowym. |
| `RS` | Siła względna na tle listy (0–100). |
| `ATR` | Dzienna zmienność w % ceny. |
| `Stop`, `Target` | Proponowany stop i cele (np. 2R i 3R). |
| `Size` | Ile sztuk kupić, żeby trafienie w stop kosztowało `risk_pct` konta. |
| `Edge` | Jak ostatni sygnał na tym instrumencie wypadał w przeszłości (patrz [Edge](#58-edge--który-sygnał-miał-przewagę)). |

Kolumny sortujesz kliknięciem w nagłówek. Przycisk **Export CSV** zapisuje wyniki do pliku, a **Refresh** przelicza skan na nowo.

**Jak liczony jest `Score`.**

```
score = suma wag świeżych sygnałów
      + premia, gdy trend dzienny jest zgodny (minus, gdy przeciwny)    # cena vs SMA200, SMA50 vs SMA200
      + premia, gdy trend tygodniowy jest zgodny (minus, gdy przeciwny) # 30-tygodniowa średnia
      + premia, gdy siła względna jest w górnych 20% (long) lub dolnych 20% (short)
```

Wagi rodzin domyślnie: breakout 1,5; trend, momentum, mean reversion, volume po 1,0; pattern 0,5. Premie po 1,0.

**Kliknij wiersz**, a zobaczysz panel z:

- wykresem świecowym z zaznaczonymi sygnałami oraz liniami stopu i celów,
- planem ryzyka,
- rozbiciem wyniku (skąd wzięły się punkty),
- historią każdego z zadziałanych sygnałów na tym instrumencie.

**Przykład.** Skanujesz listę `us_large` w dzień, gdy baner mówi *risk-on*. Na górze tabeli jest `NVDA`, long, wynik 4,5: sygnał `donchian_breakout` (1,5) + `golden_cross` (1,0) + premia za trend dzienny (1,0) + trend tygodniowy (1,0) = 4,5. Plan: stop 7,40 $ poniżej ceny, cel 2R, rozmiar 120 sztuk. Klikasz wiersz, patrzysz na wykres: czy wybicie wygląda czysto? Jak sygnał wypadał na tym instrumencie w przeszłości? Dopiero potem decydujesz.

**Co Ci to daje.** Zamiast szukać okazji, dostajesz posortowaną listę z gotowym planem ryzyka. Baner reżimu przypomina, czy rynek w ogóle sprzyja Twojemu kierunkowi.

**Uwaga.** Skanuj **po zamknięciu sesji**; podczas notowań ostatnia świeca jeszcze się tworzy i sygnał może zniknąć do zamknięcia.

---

### 5.2 Backtest — czy ten pomysł działał w przeszłości

**Po co.** Odpowiada na pytanie „co by się stało, gdybym przez ostatnie lata stosował tę regułę na tym instrumencie?”. Uwzględnia koszty, stopy, cele i sposób wejścia.

**Jak użyć.**

1. Podaj **ticker** (np. `SPY`) i **sygnał** (np. `donchian_breakout`).
2. Wybierz **silnik**: `vectorized` (szybki, domyślny), `cerebro` (referencyjny, wolniejszy) lub oba, by zobaczyć je obok siebie.
3. Opcjonalnie dodaj **filtry wejścia** (trend, rynek, ADX, wolumen, zmienność), wybierz **sposób wejścia** (po otwarciu, zlecenie stop, zlecenie limit) i **wyjścia** (cel, czas, trailing, kanał, breakeven, RSI, średnie, Supertrend, nieudane wybicie, brak postępu). Szczegóły: [rozdział 8](#8-reguły-backtestu-filtry-wejścia-wyjścia-pyramiding).
4. Opcjonalnie włącz **pyramiding**.
5. Zmień parametry sygnału i reguł, jeśli chcesz.
6. Naciśnij **Run backtest**.

Za stop zawsze odpowiada **początkowy stop ATR** (domyślnie 2 × ATR od ceny odniesienia); określa on także, ile wynosi 1R.

**Co zobaczysz.**

- **Kluczowe metryki:** łączny zwrot, CAGR, Sharpe, Sortino, max drawdown, liczba transakcji, win rate, profit factor, expectancy w R, SQN, ekspozycja, buy & hold (słownik: [rozdział 2](#2-słowniczek)).
- **Krzywa kapitału** na tle buy & hold.
- **In-sample vs. out-of-sample:** te same metryki osobno dla „starszej” i „młodszej” części historii. Patrz [rozdział 9](#9-jak-czytać-wyniki-i-nie-dać-się-oszukać).
- **Monte Carlo** transakcji (kolejna sekcja niżej).
- **Transakcje na wykresie** (z każdym dokupieniem) i w sortowalnej tabeli, z powodem zamknięcia: `stop`, nazwa reguły wyjścia lub `open` (jeszcze otwarta).
- Przycisk **Pin run**, który zapisuje wynik do porównania (Compare).

**Monte Carlo na ekranie Backtest.** Program tasuje Twoje zamknięte transakcje (w R) tysiąc razy dwiema metodami:

- *shuffled*: te same transakcje w losowej kolejności. Łączny zysk jest ten sam, zmienia się **najgłębsze obsunięcie** i **najdłuższa seria strat**.
- *bootstrapped*: losowanie ze zwracaniem. Zmienia się także łączny zysk.

Dla każdej metody widzisz wynik „pechowy” (5. percentyl), medianę i „szczęśliwy” (95. percentyl) oraz **szansę ruiny**, czyli odsetek symulacji, w których obsunięcie sięgnęło 50% (próg zmienisz w `monte_carlo.ruin_drawdown_pct`). Potrzeba co najmniej dwóch zamkniętych transakcji.

**Przykład.** `SPY` + `connors_rsi2_long` (kup, gdy RSI(2) < 10, a cena jest nad średnią 200 dni), wejście `next_open`, wyjścia `target, time`, silnik `both`. Dostajesz 140 transakcji, win rate 71%, expectancy +0,18R, max drawdown −9%. Obie krzywe silników się pokrywają, więc wiesz, że szybki silnik liczy poprawnie. W *out-of-sample* expectancy spada do +0,11R: słabiej, ale nadal dodatnio. To bardziej uczciwy obraz niż sama liczba z całej historii. Monte Carlo mówi, że w pechowym scenariuszu obsunięcie byłoby −16%, a szansa spadku o 50% to 0%.

**Co Ci to daje.** Wiesz, czy pomysł ma jakąkolwiek przewagę, jak bardzo „boli” i czy wynik nie jest tylko szczęściem co do kolejności transakcji.

**Dobre praktyki.**

- Wyniki z mniej niż 20 transakcjami są głównie szumem, program oznacza je ostrzeżeniem.
- Nie dostrajaj w nieskończoność. Patrz sekcja o overfittingu.

---

### 5.3 Sweep — które ustawienie jest najlepsze

**Po co.** Powtarza ten sam backtest dla wielu wartości jednego lub dwóch parametrów i pokazuje wyniki jako **mapy cieplne**. Odpowiada na pytanie „czy wynik zależy od dokładnego ustawienia, czy działa w szerokim przedziale?”.

**Jak użyć.**

1. Przygotuj setup jak w Backtest.
2. Dodaj **oś** (axis): wybierz, co zmieniasz (parametr sygnału, filtra, wejścia, wyjścia, stopu, pyramidingu albo kosztów) i podaj zakres (`od:do:krok`, np. `4:16:2`) albo listę wartości (`1,2,3`). Druga oś tworzy siatkę.
3. Wybierz **metrykę** do pokolorowania.
4. **Run sweep**.

**Limity:** do 200 kombinacji, 2–50 wartości na parametr. Wszystko liczone jest na wszystkich rdzeniach procesora; 200 kombinacji na 10 latach danych trwa kilka sekund. Nie da się „sweepować” udziału out-of-sample, bo on definiuje podział.

**Co zobaczysz.** **Dwie mapy:** jedną dla okresu in-sample, drugą dla out-of-sample, kolorowane wybraną metryką. Kliknij komórkę: zobaczysz jej metryki, **średnią jej sąsiadów** (to ważne, o czym niżej) i link, który otwiera to ustawienie w Backtest. Kombinacja łamiąca regułę (np. szybka średnia dłuższa niż wolna) pokazana jest jako nieudana, a reszta liczy się dalej.

**Jak czytać.** Szukasz **plateau**, czyli dużego, zielonego obszaru, a nie pojedynczego jaskrawego punktu. Samotny szczyt otoczony słabymi komórkami to prawie na pewno dopasowanie do szumu. Porównaj obie mapy: wzór widoczny w obu to dobry znak, wzór tylko w in-sample to ostrzeżenie.

**Przykład.** Sweep `connors_rsi2_long` na `SPY` z osiami `signal.oversold = 4:16:2` i `exit.target.target_r = 1,2,3`, metryka `expectancy_r`. Zielony pas przy `oversold` 8–12 w obu mapach: ustawienie domyślne (10) leży w środku plateau, więc jest odporne. Gdyby jedynie komórka `oversold=6, target=3` była zielona, nie ufałbyś jej.

**Co Ci to daje.** Zamiast zgadywać, widzisz „krajobraz” wyników i możesz wybrać ustawienie w stabilnym obszarze.

---

### 5.4 Walk-forward — bardziej uczciwy test niż Sweep

**Po co.** Sweep wybiera ustawienie, patrząc na całą historię, więc nawet wynik out-of-sample bywa „podejrzany”, gdy zerkasz na niego raz po raz. Walk-forward działa tak, jak działałbyś w życiu: **stroisz na starszym kawałku i handlujesz następnym, którego nie widziałeś, a potem przesuwasz okno i powtarzasz**. Wyniki z kolejnych „egzaminów” sklejane są w jedną krzywą.

**Jak użyć.** Te same pola co w Sweep (setup + osie), plus:

| Pole | Znaczenie | Domyślnie |
| --- | --- | --- |
| Windows | Ile okien out-of-sample (egzaminów). | 5 |
| In-sample windows (ratio) | Ile razy dłuższe jest okno „uczenia” od okna egzaminu. | 3 |
| Scheme | `rolling`: okno uczenia o stałej długości, przesuwane. `anchored`: zawsze od pierwszej świecy, rośnie. | rolling |
| Pick by | Metryka, wg której okno wybiera ustawienie (np. Sharpe). | Sharpe |
| Min trades | Ile zamkniętych transakcji musi mieć ustawienie, żeby mogło być wybrane. | 10 |

Naciśnij **Run walk-forward**. Limit: maksymalnie 2000 backtestów, 10–20 sekund na 10 latach danych.

**Co zobaczysz.**

- Metryki **sklejonej krzywej out-of-sample** obok „niezmienionego setupu” (te same wartości, handlowane na tych samych świecach) i buy & hold.
- **Walk-forward efficiency**: roczny zysk (CAGR) sklejonej krzywej podzielony przez średni CAGR in-sample wybranych ustawień. Bliska 1 (lub wyższa) = to, co działało w uczeniu, działa też w egzaminie. Znacznie poniżej 1 = piki in-sample były szczęściem.
- Krzywe na jednym wykresie z zaznaczonymi początkami okien.
- Tabelę **każdego okna**: daty, wybrane ustawienie, wynik in-sample i out-of-sample, liczba transakcji i świec.
- **Ustawienie „na następny okres”**, wybrane na ostatnim oknie uczenia, z linkiem do Backtest.
- Transakcje out-of-sample i eksport CSV.

**Jak czytać.** Jeśli wybrane ustawienie **skacze** od okna do okna (raz `oversold=6`, raz `14`), a efficiency jest daleko poniżej 1, to najlepsze ustawienie in-sample nie przenosi się na przyszłość. Okno, w którym żadne ustawienie nie spełnia `min trades`, trzyma gotówkę.

**Przykład.** `SPY`, `connors_rsi2_long`, oś `signal.oversold = 5:25:2.5` i `exit.target.target_r = 1:3:0.5`, 5 okien. Sklejony Sharpe: 0,8; niezmieniony setup: 0,9; efficiency 0,85. Wnioski: strojenie niewiele dało (niezmieniony setup radzi sobie niemal tak samo), a wynik jest stabilny. To dobry znak dla samej reguły.

**Co Ci to daje.** Najbardziej realistyczną odpowiedź na pytanie „czy strojenie parametrów ma sens, czy tylko dopasowuję się do przeszłości?”.

---

### 5.5 Watchlist — ten sam pomysł na wielu instrumentach

**Po co.** Reguła, która działa na jednym instrumencie, może być przypadkiem. Ten ekran uruchamia **ten sam setup na każdym instrumencie listy** (albo na własnych tickerach) i pokazuje, **jak wyniki się rozkładają**.

**Jak użyć.** Setup jak w Backtest, bez tickera (ticker zastępuje lista). Naciśnij **Run on every ticker**. Liczony jest silnik vectorized na wielu rdzeniach; 20 ETF-ów na 10 latach to kilka sekund, gdy dane są w pamięci podręcznej.

**Co zobaczysz.**

- **Rozrzut metryki** (wybierasz ją w polu `Rank by`): najgorszy, 25. percentyl, mediana, 75. percentyl, najlepszy wynik, osobno in-sample i out-of-sample, oraz **odsetek instrumentów powyżej progu opłacalności** (0 dla zwrotów, Sharpe, Sortino, expectancy, SQN; 1 dla profit factor).
- **Transakcje zebrane razem** (w R): win rate, expectancy, profit factor i SQN dla wszystkich instrumentów naraz. Zyski w pieniądzach nie są sumowane, bo konto każdego instrumentu liczy się osobno.
- **Tabelę** metryk każdego instrumentu; kliknięcie instrumentu otwiera jego backtest. Instrumenty z małą liczbą transakcji są oznaczone.

Filtr „rynek” porównuje benchmark z setupu, a jeśli go nie ma, benchmark listy (linia `# benchmark:` w pliku), a w ostateczności `scan.benchmark`.

**Przykład.** `connors_rsi2_long` na liście `etf` (20 funduszy). Mediana expectancy +0,12R, 17 z 20 funduszy powyżej zera w out-of-sample, a zebrane transakcje dają profit factor 1,4. Reguła działa szeroko, a nie dzięki jednemu funduszowi. Gdyby dwa fundusze miały +1R, a 18 poniżej zera, byłby to wynik „dopasowany do dwóch”.

**Co Ci to daje.** Sprawdzasz **szerokość** działania pomysłu. Strategia dobra na wielu niezależnych instrumentach jest o wiele bardziej wiarygodna niż dobra na jednym.

---

### 5.6 Portfolio — jedno konto, wiele pozycji

**Po co.** W Watchlist każdy instrument ma osobne, wyimaginowane konto. W prawdziwym życiu masz **jedno konto i ograniczoną liczbę pozycji**. Portfolio symuluje to: sygnały z całej listy konkurują o te same miejsca i te same pieniądze.

**Jak użyć.** Setup jak w Watchlist (bez pyramidingu), plus parametry portfela:

| Pole | Znaczenie | Domyślnie |
| --- | --- | --- |
| Max positions | Ile pozycji otwartych (łącznie ze zleceniami czekającymi na wypełnienie) naraz. | 10 |
| Max exposure | Łączna wartość pozycji jako % konta; powyżej 100% to dźwignia. | 100% |
| Priority | Reguła decydująca, który sygnał wchodzi pierwszy, gdy odezwie się ich więcej, niż jest miejsc. | `relative_strength` |
| Engines | `vectorized`, `cerebro` lub oba. | vectorized |

**Reguły priorytetu.**

| Priorytet | Jak szereguje (najwyższy pierwszy) |
| --- | --- |
| `relative_strength` | Zwroty z 63/126/189/252 świec z wagami 0,4/0,2/0,2/0,2 (styl IBD). Dla short: najniższa pierwsza. |
| `momentum` | Zwrot od 252 do 21 świec temu („12 minus 1 miesiąc”). Dla short: najniższy pierwszy. |
| `score` | Wynik zbieżności ze Scannera w dniu sygnału. Ma dodatkowe pola: ustawienia punktacji, trendu i świeżości, oraz parametry i wagę każdego sygnału. Wyniki zmieniają się skokowo, więc remisy są częste (remis rozstrzyga kolejność listy). Liczy się wolniej (ok. 0,1 s na instrument z 10 lat). |

**Jak decyduje portfel w każdym dniu:** sygnały instrumentów z już otwartą pozycją są ignorowane; reszta jest szeregowana; sygnał dostaje zlecenie, dopóki pozycje + czekające zlecenia są poniżej limitu; wielkość liczona jest ze wspólnego kapitału, a gdy przekroczyłaby limit ekspozycji, jest zmniejszana (a przy mniej niż jednym lot-cie pomijana). Pominięte sygnały są liczone.

**Co zobaczysz.** Metryki konta wobec buy & hold benchmarku, liczbę **pominiętych sygnałów**, kapitał i liczbę otwartych pozycji w czasie, metryki in-sample/out-of-sample, **wkład każdego instrumentu** (klik otwiera jego backtest) i wszystkie transakcje. Przycisk **Pin run** zapisuje przebieg pokazanego silnika do porównania.

**Cerebro w Portfolio** jest wolny: około minuty na 20 instrumentów z 10 lat. Silnik vectorized przelicza cały S&P 500 z 10 lat w niecałą minutę (przy danych w pamięci podręcznej). Oba mają dawać te same transakcje.

**Przykład.** `donchian_breakout` na `sp500`, filtr `trend`, `max positions` 10, priorytet `momentum`. Wynik: zwrot +95% przy drawdown −22%, 41% sygnałów pominiętych z braku miejsc. Mówi Ci to, że strategia „chciała” kupować znacznie więcej, niż portfel mógł pomieścić, i że to priorytet decydował o jakości wyboru. Zmieniasz priorytet na `relative_strength`, naciskasz **Pin run**, i porównujesz obie wersje w Compare.

**Co Ci to daje.** Wynik przybliżony do realnego: z limitami kapitału i pozycji. To zwykle pierwszy moment, w którym „super strategia” z Watchlist okazuje się przeciętna, bo nie da się grać wszystkim naraz.

---

### 5.7 Rotation — trzymaj najsilniejszych

**Po co.** To zupełnie inna filozofia niż sygnały: **bez wejść, stopów i celów**. Raz w tygodniu lub miesiącu program sprawdza, które instrumenty z listy są najsilniejsze (rosły najmocniej), trzyma kilka najlepszych i wymienia resztę. Jeśli „najsilniejszy” instrument sam traci (momentum bezwzględne ≤ 0), jego miejsce zajmuje bezpieczne aktywo (np. obligacje `TLT`) albo gotówka.

**Jak użyć.**

| Pole | Znaczenie | Domyślnie |
| --- | --- | --- |
| Ranking rule | Jak szeregować: `momentum` (zwrot 12 miesięcy bez ostatniego miesiąca) lub `relative_strength` (styl IBD). | momentum |
| Holdings | Ile instrumentów trzymać. | 5 |
| Rebalance | `weekly` lub `monthly`, w ostatnim dniu tygodnia/miesiąca. | monthly |
| Weighting | `equal` (po równo) lub `inverse_volatility` (mniej tam, gdzie większa zmienność; okno 63 świec). | equal |
| Absolute momentum lookback | Po ilu świecach sprawdzać, czy wybrany instrument w ogóle rośnie; 0 wyłącza. | 252 |
| Safe asset | Co trzymać w miejsce „odrzuconych”; puste = gotówka. | gotówka |
| Benchmark | Do porównania buy & hold. | benchmark listy |
| Koszty | Prowizja i poślizg. | 0,1% / 0,05% |
| Engines | `vectorized`, `cerebro` lub oba. | vectorized |

Naciśnij **Run rotation**.

**Co zobaczysz.** Metryki wobec buy & hold benchmarku; **udział trzymany defensywnie** (w bezpiecznym aktywie lub gotówce); **obrót** (turnover rocznie, w % średniego kapitału); średnią liczbę pozycji; kapitał i skład portfela w czasie; **co wybrałby rebalans na ostatnim zamknięciu** (czyli „co kupić teraz”); metryki in-sample i out-of-sample; wkład każdego instrumentu; wszystkie „holdingi”. Przycisk **Pin run** zapisuje przebieg do Compare.

**Szczegóły warte wiedzy.**

- „Transakcja” to jeden holding: od zakupu otwierającego pozycję do sprzedaży, która ją zamyka. Nie ma stopu, więc nie ma R, a **expectancy i SQN są puste**; win rate i profit factor liczone są na holdingach.
- Gotówka nie zarabia (brak oprocentowania).
- Bieg zaczyna się od pierwszego rebalansu, na którym da się wybrać instrument, więc rozgrzewka wskaźników nie liczy się jako czas w gotówce.

**Przykład.** Lista `etf`, `holdings` 3, `weighting` `inverse_volatility`, `safe asset` `TLT`. Wynik: zwrot +70% przy drawdown −14% (buy & hold benchmarku: −24%), 22% czasu defensywnie, obrót 180% rocznie. Widzisz, że rotacja ogranicza obsunięcia kosztem częstych transakcji; sprawdzasz, ile kosztów je zjada.

**Co Ci to daje.** Prostą, długoterminową strategię trzymania liderów, którą możesz obsługiwać raz w miesiącu, oraz gotową odpowiedź „co teraz trzymać”.

---

### 5.8 Edge — który sygnał miał przewagę

**Po co.** Odpowiada na pytanie: „czy po tym sygnale cena zachowywała się inaczej niż w zwykłym dniu?”. Dla każdego sygnału, zebranego z całej listy, liczy, jak wyglądał zwrot po 5, 10 i 20 świecach (domyślnie; horyzonty możesz zmienić).

**Jak użyć.** Wybierz listę, opcjonalnie rodziny i kierunek, **Horizons (bars)** (po ilu świecach mierzyć), **Min events** (ukryj sygnały z małą liczbą zdarzeń). **Compute edge**.

**Jak czytać tabelę.** Dla każdego horyzontu `h` kolumny: `N` (ile było zdarzeń), `Win` (odsetek zakończonych zyskiem), `Avg` (średni zwrot), **`vs base`** (różnica względem **średniego zwrotu losowej świecy** tego samego instrumentu, czyli właściwa „przewaga”). Zwrot liczony jest od **otwarcia następnej świecy** (tak, jak realnie byś wszedł) do zamknięcia po `h` świecach, w kierunku sygnału. Komórki są pokolorowane wg przewagi.

**Przykład.** `donchian_breakout`: `N 10d` = 1 840 zdarzeń, `Win 10d` = 53%, `Avg 10d` = +0,9%, `vs base 10d` = +0,4 pp. Czyli po wybiciu cena rosła średnio o 0,4 punktu procentowego więcej niż w zwykłym dniu. Mała przewaga, ale oparta na wielu zdarzeniach. Sygnał z `N` = 12 to anegdota.

**Co Ci to daje.** Zanim zbudujesz strategię na sygnale, wiesz, czy w ogóle coś niósł. Scanner pokazuje w kolumnie `Edge` ten sam rodzaj informacji dla ostatniego sygnału na instrumencie.

**Uwaga: błąd przetrwania.** Listy w programie zawierają **dzisiejszych** członków indeksów, więc statystyki są lekko zawyżone (patrz [rozdział 14](#14-ograniczenia-o-których-musisz-wiedzieć)).

---

### 5.9 Compare — porównanie przypiętych wyników

**Po co.** Testowanie to seria wariantów: „co, jeśli cel 3R zamiast 2R? co, jeśli dodam filtr trendu?”. Compare zestawia je **obok siebie**, wskazując dokładnie, czym się różnią.

**Jak użyć.**

1. Na ekranie Backtest, Portfolio lub Rotation uruchom test i naciśnij **Pin run**.
2. Zmień jeden parametr, uruchom ponownie, **Pin run** znów.
3. Wejdź w **Compare**.

Przypiąć można **do 8 przebiegów**. Przycisk zmienia się na **Unpin**, gdy przebieg jest przypięty.

**Co zobaczysz.**

- **Różniące się parametry**: tylko te, które się różnią, żebyś od razu widział, co zmieniłeś. Dla portfela także uniwersum, limity, priorytet z parametrami; dla rotacji uniwersum, holdingi, rebalans, bezpieczne aktywo, reguły rankingu i ważenia, benchmark.
- **Sprawdzenie out-of-sample:** metryki in-sample obok out-of-sample.
- **Sprawdzenie Monte Carlo** (dla backtestów): wynik pechowy i medianowy, obsunięcie, seria strat, szansa ruiny, osobno dla każdej metody. Portfele i rotacje nie mają Monte Carlo.
- **Każda metryka**, dla całej historii lub dla jednego okresu (przełącznik **Period**), z **najlepszą wartością podświetloną**.
- **Statystyki portfela** (otwarte pozycje, ekspozycja, pominięte sygnały) i **rotacji** (holdingi, udział defensywny, obrót, koszty) dla tego samego okresu.
- **Krzywe zwrotu** wszystkich przebiegów na jednym wykresie.

**Przyciski.**

| Przycisk | Co robi |
| --- | --- |
| **Open in Backtest / Open in Portfolio / Open in Rotation** | Uruchamia przypięty setup **ponownie, na dzisiejszych danych** i z kontem ustawionym w nagłówku. |
| **Log a trade** | Otwiera Journal z wybranym tym przebiegiem (patrz niżej). |
| **Export JSON / Import JSON** | Zapisuje przypięte przebiegi do pliku lub je z niego wczytuje (np. jako kopię lub do przeniesienia na inny komputer). |
| **Remove all** | Usuwa wszystkie przypięte. |

**Przypięty przebieg to zdjęcie.** Zachowuje wynik, który widziałeś, nawet gdy napłyną nowe świece. Przebiegi przypięte zanim pojawiły się wyniki out-of-sample lub Monte Carlo nie mają tych sekcji, bo przypięcie nigdy nie przelicza się ponownie.

**Przykład.** Przypinasz `donchian_breakout` na `QQQ` z wyjściem `target` 2R, potem to samo z `trailing` i potem z `trailing` + filtr `trend`. W Compare widzisz w tabeli parametrów tylko wiersze „exits” i „filters”. Wersja z filtrem ma najwyższy Sharpe (podświetlony na zielono), ale tylko 14 transakcji, więc dostaje ostrzeżenie „mało transakcji”; wniosek: obiecujące, ale niepewne.

**Co Ci to daje.** Zamiast notować wyniki w notatniku, masz tabelę, w której widać, **która zmiana naprawdę coś dała**.

---

### 5.10 Journal — dziennik prawdziwych transakcji

**Po co.** Backtest mówi, co *powinno* się zdarzyć. Dziennik zapisuje, co się **zdarzyło naprawdę**, i zestawia to z backtestem, który transakcję podpowiedział. Pozwala uczciwie ocenić, czy w praktyce uzyskujesz to, co obiecywał test, i co psuje wyniki (poślizgi, emocje, pominięte sygnały).

**Jak użyć.** Naciśnij **Log a trade** (na ekranie Journal albo na przypiętym przebiegu w Compare, co od razu podpina przebieg jako „podpowiadający”). Wypełnij pola:

| Pole | Znaczenie |
| --- | --- |
| Ticker | Instrument. |
| Direction | Long lub short. |
| Entry date, Entry price | Kiedy i po ile wszedłeś. |
| Quantity | Ile sztuk. |
| Initial stop | Początkowy stop; **wyznacza 1R**. |
| Exit date, Exit price | Wyjście; **puste, gdy transakcja jest otwarta**. |
| Fees | Łączne opłaty za wejście i wyjście. |
| Suggested by | Przypięty przebieg, który transakcję podpowiedział (zachowywana jest jego kopia, więc odpięcie przebiegu niczego nie usuwa). |
| Notes | Notatki: dlaczego wszedłeś, co czułeś, czego się nauczyłeś. |

Serwer sprawdza zależności między polami (np. po której stronie ceny wejścia leży stop; wyjście musi mieć i datę, i cenę) i mówi, co jest nie tak.

**Co zobaczysz.** Dla każdej transakcji: zysk po opłatach, zwrot w % i **R** (liczone od początkowego stopu), a obok **win rate i expectancy backtestu**, który ją podpowiedział, z linkiem otwierającym ten backtest ponownie. Podsumowanie: liczba otwartych i zamkniętych transakcji, win rate, średni zwrot, średnie i łączne R zamkniętych.

**Przykład.** Wchodzisz long w `MSFT` po 400 $, stop 388 $ (1R = 12 $ na sztukę, czyli 600 $ ryzyka przy 50 sztukach), opłaty 20 $. Wychodzisz po 424 $: zysk 50 × 24 − 20 = 1 180 $, czyli nieco poniżej 2R (20 $ opłat zjada ok. 0,03R). Obok widzisz, że backtest tej reguły miał expectancy +0,2R. Ta transakcja wyszła lepiej niż średnia, jedna transakcja o niczym jednak nie przesądza. Po 30 transakcjach średnie R porównasz z backtestem: duża różnica na minus to sygnał, żeby sprawdzić wykonanie (poślizgi, spóźnione wejścia) albo samą regułę.

**Co Ci to daje.** Pętlę zwrotną: test → transakcja → porównanie. Dziennik działa w tej samej bazie co przypięte przebiegi i jest dostępny z każdej przeglądarki na tym komputerze.

> Dziennik zawiera Twoje prawdziwe transakcje. Patrz [rozdział 13](#13-bezpieczeństwo).

---

### 5.11 Signals — biblioteka sygnałów

**Po co.** Katalog wszystkich 38 sygnałów: do czego służą, jakie mają wagi i parametry. Pomaga wybrać sygnał do backtestu i zrozumieć, co oznacza nazwa w Scannerze.

**Co zobaczysz.** Dla każdego sygnału: rodzinę, kierunek, wagę w punktacji, regułę w słowach (z aktualnymi wartościami parametrów, więc „RSI(3) < 15” zawsze opisuje regułę, która faktycznie została użyta) oraz **domyślną wartość i dozwolony zakres każdego parametru**.

Pełny opis sygnałów: [rozdział 7](#7-biblioteka-sygnałów-38).

---

## 6. Scenariusze krok po kroku

### Scenariusz A: „Co obejrzeć dziś wieczorem?”

**Cel:** znaleźć kilka kandydatów po zamknięciu sesji.

1. Poczekaj do zamknięcia giełdy.
2. **Scanner** → lista (np. `sp500`) → **Scan**.
3. Spójrz na baner reżimu. Jeśli *risk-off*, a Ty szukasz long, bądź ostrożniejszy albo zmniejsz rozmiar.
4. Posortuj po `Score`. Otwórz 3–5 najwyższych (klik w wiersz) i oceń wykres: czy wybicie jest czyste? Czy stop ma sens?
5. Dla interesującego sygnału sprawdź w kolumnie `Edge`, czy w przeszłości na tym instrumencie coś znaczył.
6. Zanotuj kandydatów. **Nie kupuj tylko dlatego, że tabela jest na górze**: to lista do przejrzenia, a nie rekomendacja.

**Efekt:** 10 minut zamiast godziny.

### Scenariusz B: „Czy ta strategia ma sens?”

**Cel:** sprawdzić pomysł od zera, krok po kroku, od najtańszego sprawdzenia do najdroższego.

1. **Edge** na liście, która Cię interesuje. Czy sygnał ma dodatnie `vs base` przy dużym `N`? Jeśli nie, zakończ.
2. **Backtest** na jednym instrumencie (np. `SPY`), silnik `both`. Czy oba silniki dają to samo? Czy jest przynajmniej 20–30 transakcji? Czy expectancy jest dodatnie **także out-of-sample**?
3. **Watchlist** (to samo na całej liście). Czy wynik jest szeroki, czy trzymają go dwa instrumenty?
4. **Sweep** po jednym kluczowym parametrze. Czy jest plateau?
5. **Walk-forward**. Czy strojenie w ogóle pomaga? Czy efficiency jest bliska 1?
6. **Portfolio**, gdy chcesz grać na wielu instrumentach naraz. Co z limitem pozycji?

Każdy kolejny krok jest droższy i bardziej wymagający, więc najpierw odrzucasz pomysły słabe, a dopiero potem inwestujesz czas w silne.

### Scenariusz C: „Jaka wersja jest lepsza?”

**Cel:** porównać warianty tej samej strategii.

1. **Backtest** → ustaw wariant 1 → **Run backtest** → **Pin run**.
2. Zmień jedną rzecz (np. dodaj filtr `trend`) → uruchom → **Pin run**.
3. Powtórz dla innych wariantów (do 8).
4. **Compare**: najpierw tabela różnic (czy na pewno zmieniłeś tylko to, co chciałeś), potem metryki z podświetleniem najlepszej wartości, potem sprawdzenie out-of-sample i Monte Carlo.
5. Wybierając zwycięzcę, **nie patrz tylko na zysk**: zerknij na drawdown, liczbę transakcji i out-of-sample.

**Zasada:** zmieniaj **jedną rzecz naraz**. Inaczej nie wiesz, co dało efekt.

### Scenariusz D: „Zapisuję prawdziwą transakcję i śledzę wyniki”

1. W Compare przy przypiętym przebiegu naciśnij **Log a trade**.
2. Journal otworzy się z wypełnionym tickerem i podpiętym przebiegiem. Uzupełnij cenę wejścia, ilość i **początkowy stop** (od niego liczy się R).
3. Zapisz. Gdy zamkniesz pozycję, wróć, dopisz datę i cenę wyjścia oraz opłaty.
4. Po kilkunastu–kilkudziesięciu transakcjach spójrz na podsumowanie: średnie R i win rate zestawiasz z backtestem, który transakcje podpowiadał.

### Scenariusz E: „Strategia na raz w miesiącu”

1. **Rotation** → lista `etf` → ranking `momentum`, `holdings` 3, rebalans `monthly`, `safe asset` `TLT`.
2. **Run rotation**; porównaj drawdown i zwrot z benchmarkiem; sprawdź obrót i udział defensywny.
3. Gdy wynik Cię przekonuje, patrz w sekcję „co wybrałby rebalans na ostatnim zamknięciu”. To lista na dziś.
4. Powtarzaj raz w miesiącu, w ostatnim dniu miesiąca.

### Scenariusz F: „Aktualizuję listy indeksów”

Skład indeksów zmienia się co kwartał. Raz na jakiś czas wpisz:

```bash
tradescan update-universes
```

Program pobierze aktualne składy S&P 500 i Nasdaq-100 z Wikipedii, pokaże, które tickery doszły, a które odpadły, przeliczy format (`BRK.B` → `BRK-B`) i zapisze pliki. Jeśli pobieranie lub sprawdzenie poprawności się nie powiedzie, **stary plik zostaje**.

---

## 7. Biblioteka sygnałów (38)

**Sygnał** to prosta reguła sprawdzana na zamknięciu świecy, np. „cena zamknęła się powyżej najwyższego maksimum z 20 dni”. Liczy się tylko **pierwsza świeca serii**: jeśli warunek jest spełniony kilka dni z rzędu, to zdarzeniem jest pierwszy z nich. Dzięki temu sygnały można zliczać, punktować i testować w ten sam sposób. Wszystkie wskaźniki są „przyczynowe”, czyli nie zaglądają w przyszłość (test automatyczny pilnuje, żeby dodanie przyszłych świec nigdy nie zmieniało dawnych sygnałów).

Sygnały dzielą się na **6 rodzin** i mają kierunek (long / short). Każda rodzina ma domyślną wagę w punktacji Scannera. Każdą liczbę (okres, próg) możesz zmienić w interfejsie; poniżej podaję wartości domyślne.

### Jak wybrać rodzinę do swojego stylu

| Rodzina | Filozofia | Kiedy zwykle działa | Typowy pomysł na wyjście |
| --- | --- | --- | --- |
| **trend** | „Trend jest Twoim przyjacielem”. Wchodzisz, gdy trend się zaczyna lub potwierdza. | Rynki z długimi trendami. W rynku bocznym generuje fałszywe sygnały. | `trailing`, `channel`, `sma_trend`, `supertrend`. |
| **momentum** | „Siła rodzi siłę”: wchodzisz, gdy ruch nabiera tempa lub wraca po korekcie. | Rynki z wyraźnym impetem. | Cel + czas lub trailing. |
| **breakout** (wybicie) | Cena wychodzi z konsolidacji lub bije maksima, więc zaczyna się ruch. | Początek trendu; zawodzi przy fałszywych wybiciach. | `trailing`, `failed_breakout`, `no_progress`. |
| **mean_reversion** (powrót do średniej) | „Za dużo, za szybko, więc wróci”. Kupujesz wyprzedanie w trendzie wzrostowym. | Rynki o umiarkowanym trendzie; krótkie transakcje. | `target`, `time`, `rsi`, `sma_revert`. |
| **volume** | Duży wolumen potwierdza, że za ruchem stoi kapitał. | Jako potwierdzenie. | Cel + czas. |
| **pattern** (formacje świecowe) | Konkretne układy świec: objęcie, gap. | Słabsze, stąd mała waga (0,5). | Krótki cel/czas. |

### Trend (waga rodziny 1,0)

| Sygnał | Kier. | Co oznacza | Parametry (domyślnie) |
| --- | --- | --- | --- |
| `golden_cross` | long | Średnia 50-dniowa przecina od dołu średnią 200-dniową. Klasyczny sygnał początku długoterminowego trendu wzrostowego. | `fast`=50, `slow`=200 |
| `death_cross` | short | Średnia 50 przecina od góry średnią 200. | `fast`=50, `slow`=200 |
| `ema_cross_up` | long | EMA(9) przecina w górę EMA(21): szybszy, krótkoterminowy trend. | `fast`=9, `slow`=21 |
| `ema_cross_down` | short | EMA(9) przecina w dół EMA(21). | `fast`=9, `slow`=21 |
| `adx_di_up` | long | Wskaźnik kierunkowy +DI przecina w górę −DI, **gdy ADX ≥ 20**, czyli trend jest wystarczająco wyraźny. | `period`=14, `min_adx`=20 |
| `adx_di_down` | short | −DI przecina w górę +DI przy ADX ≥ 20. | `period`=14, `min_adx`=20 |
| `supertrend_up` | long | Wskaźnik Supertrend zmienia kolor z „spadkowego” na „wzrostowy”. | `period`=10, `mult`=3,0 |
| `supertrend_down` | short | Supertrend zmienia się ze wzrostowego na spadkowy. | `period`=10, `mult`=3,0 |

### Momentum (waga rodziny 1,0)

| Sygnał | Kier. | Co oznacza | Parametry (domyślnie) |
| --- | --- | --- | --- |
| `macd_cross_up` | long | Linia MACD przecina w górę swoją linię sygnału: przyspieszenie wzrostu. | `fast`=12, `slow`=26, `signal`=9 |
| `macd_cross_down` | short | MACD przecina w dół linię sygnału. | j.w. |
| `rsi_reversal_up` | long | RSI(14) wraca powyżej 30, czyli wychodzi ze strefy wyprzedania. | `period`=14, `oversold`=30 |
| `rsi_reversal_down` | short | RSI(14) wraca poniżej 70, czyli wychodzi ze strefy wykupienia. | `period`=14, `overbought`=70 |

### Breakout / wybicie (waga rodziny 1,5)

| Sygnał | Kier. | Co oznacza | Parametry (domyślnie) |
| --- | --- | --- | --- |
| `donchian_breakout` | long | Zamknięcie powyżej najwyższego maksimum z poprzednich 20 świec. To wejście „Żółwi” (Turtle). | `period`=20 |
| `donchian_breakdown` | short | Zamknięcie poniżej najniższego minimum z poprzednich 20 świec. | `period`=20 |
| `high_52w_breakout` | long | Nowe 252-dniowe maksimum **przy wolumenie ≥ 1,5× średniej 50-dniowej**. Maksimum roczne potwierdzone wolumenem. | `period`=252, `volume_period`=50, `min_rvol`=1,5 |
| `nr7_breakout` | long | Zamknięcie powyżej maksimum świecy o najwęższym zakresie z 7 ostatnich (NR7): po „ściśnięciu” często przychodzi ruch. | `lookback`=7 |
| `nr7_breakdown` | short | Zamknięcie poniżej minimum świecy NR7. | `lookback`=7 |
| `squeeze_release_up` | long | Pasma Bollingera wychodzą z wnętrza kanału Keltnera po co najmniej 5 świecach „ściśnięcia”, a cena jest powyżej środka (TTM squeeze). | `period`=20, `bb_mult`=2,0, `kc_mult`=1,5, `min_squeeze_bars`=5 |
| `squeeze_release_down` | short | To samo, cena poniżej środka. | j.w. |

### Mean reversion / powrót do średniej (waga rodziny 1,0)

| Sygnał | Kier. | Co oznacza | Parametry (domyślnie) |
| --- | --- | --- | --- |
| `connors_rsi2_long` | long | RSI(2) < 10, **gdy cena jest nad średnią 200-dniową**: gwałtowne wyprzedanie w trendzie wzrostowym (strategia Connorsa). | `rsi_period`=2, `trend_period`=200, `oversold`=10 |
| `connors_rsi2_short` | short | RSI(2) > 90 przy cenie pod średnią 200-dniową: gwałtowne odbicie w trendzie spadkowym. | `overbought`=90 |
| `cumulative_rsi_long` | long | Suma RSI(2) z 2 świec < 35. Łagodniejsza wersja powyższej. | `bars`=2, `oversold`=35 |
| `cumulative_rsi_short` | short | Suma RSI(2) z 2 świec > 165. | `overbought`=165 |
| `bb_pctb_low` | long | Wskaźnik %b Bollingera < 0, czyli cena zamknęła się **pod** dolnym pasmem. | `period`=20, `mult`=2,0, `below`=0 |
| `bb_pctb_high` | short | %b > 1, czyli cena zamknęła się **nad** górnym pasmem. | `above`=1 |
| `bb_reentry_up` | long | Zamknięcie wraca nad dolne pasmo Bollingera (wejście po powrocie, a nie w trakcie spadku). | `period`=20, `mult`=2,0 |
| `bb_reentry_down` | short | Zamknięcie wraca pod górne pasmo. | j.w. |
| `ibs_low` | long | Zamknięcie w dolnych 20% zakresu świecy (Internal Bar Strength). | `zone`=0,2 |
| `ibs_high` | short | Zamknięcie w górnych 20% zakresu świecy. | `zone`=0,2 |
| `down_streak` | long | 3 niższe zamknięcia z rzędu. | `bars`=3 |
| `up_streak` | short | 3 wyższe zamknięcia z rzędu. | `bars`=3 |

### Volume / wolumen (waga rodziny 1,0)

| Sygnał | Kier. | Co oznacza | Parametry (domyślnie) |
| --- | --- | --- | --- |
| `volume_spike_up` | long | Dzień wzrostowy z wolumenem ≥ 2× średnia z 20 świec, zamknięty w górnych 25% zakresu: sygnał akumulacji. | `rvol_period`=20, `min_rvol`=2,0, `min_close_location`=0,75 |
| `distribution_day` | short | Dzień spadkowy z wolumenem ≥ 2× średnia, zamknięty w dolnych 25% zakresu: sygnał dystrybucji (wyprzedawania). | `max_close_location`=0,25 |
| `pocket_pivot` | long | Wolumen dnia wzrostowego wyższy niż wolumen **każdego** dnia spadkowego z ostatnich 10 świec, a cena powyżej SMA(50). | `lookback`=10, `trend_period`=50 |

### Pattern / formacje (waga rodziny 0,5)

| Sygnał | Kier. | Co oznacza | Parametry (domyślnie) |
| --- | --- | --- | --- |
| `bullish_engulfing` | long | Świeca wzrostowa „obejmuje” poprzednią spadkową po korekcie pod SMA(20). | `trend_period`=20 |
| `bearish_engulfing` | short | Świeca spadkowa obejmuje poprzednią wzrostową po wzroście nad SMA(20). | `trend_period`=20 |
| `gap_and_go_up` | long | Luka w górę ≥ 2%, dzień zamyka się nad otwarciem, a wolumen ≥ 1,5× średnia z 20 świec. | `min_gap_pct`=2,0, `rvol_period`=20, `min_rvol`=1,5 |
| `gap_and_go_down` | short | Luka w dół ≥ 2%, zamknięcie pod otwarciem, wolumen ≥ 1,5× średnia. | j.w. |

**Wagi pojedynczych sygnałów** możesz nadpisać w `settings.toml` w sekcji `[scoring.signal_weights]` (np. `golden_cross = 2.0`).

**Praktyczna rada:** nie zaczynaj od najbardziej skomplikowanego sygnału. `donchian_breakout` (trend/wybicie) i `connors_rsi2_long` (powrót do średniej) to dwa klasyczne, proste przykłady o przeciwnych filozofiach; dobrze się na nich uczyć programu.

---

## 8. Reguły backtestu: filtry, wejścia, wyjścia, pyramiding

Backtest składa się z czterech klocków, które dobierasz niezależnie:

```
SYGNAŁ  →  (FILTRY WEJŚCIA)  →  WEJŚCIE  →  początkowy STOP ATR  +  (WYJŚCIA)  →  zamknięcie
 kiedy       czy wolno          jak kupić    zawsze włączony        dodatkowe        i powód
 sygnał      grać teraz         (typ zlecenia)                      reguły wyjścia   zamknięcia
```

Oba silniki czytają te same, wyliczone z góry poziomy i realizują je tak samo.

### 8.1 Filtry wejścia (domyślnie: żadnych)

Filtr to dodatkowy warunek: sygnał wolno zagrać tylko wtedy, gdy filtr mu pozwala **na zamknięciu tej samej świecy**. Zablokowany sygnał jest ignorowany, nawet jeśli filtr zezwoli na następnych świecach. Gdy wybierzesz kilka filtrów, **wszystkie** muszą zezwolić.

| Filtr | Sygnał może być zagrany, gdy | Parametry (domyślnie) | Po co |
| --- | --- | --- | --- |
| `trend` | zamknięcie jest nad SMA(`period`) (dla short pod nią) | `period`=200 | Nie kupuj „spadających noży”; graj z trendem instrumentu. |
| `market` | zamknięcie **benchmarku** jest nad jego SMA(`period`) (dla short pod nią) | `period`=200 | Nie kupuj, gdy cały rynek jest w trendzie spadkowym. Używa pola `benchmark` (domyślnie SPY, a w Watchlist/Portfolio benchmark listy). |
| `adx` | ADX(`period`) ≥ `min_adx` (w obu kierunkach) | `period`=14, `min_adx`=20 | Graj tylko, gdy jest wyraźny trend. |
| `volume` | wolumen świecy ≥ `min_ratio` × średnia z `period` świec **poprzedzających** | `period`=20, `min_ratio`=1,5 | Potwierdzenie zainteresowaniem. Instrumenty bez wolumenu (indeksy, część walut) nigdy tego filtra nie przejdą. |
| `atr_pct` | ATR mieści się między `min_pct` a `max_pct` % ceny zamknięcia | `min_pct`=1,0, `max_pct`=5,0 | Omijaj instrumenty „martwe” i „szalone”. `min_pct` musi być mniejsze od `max_pct`. |

Gdy filtrowi brakuje historii (za mało świec do policzenia wskaźnika), blokuje sygnały.

**Przykład.** `donchian_breakout` na `AAPL` z filtrami `trend, market, volume` i `--benchmark QQQ`: wybicie liczy się tylko wtedy, gdy cena `AAPL` jest nad średnią 200, `QQQ` nad swoją średnią 200 i wolumen jest ponadprzeciętny. Mniej transakcji, ale (zwykle) lepszej jakości; Compare pokaże, czy faktycznie.

### 8.2 Wejście (domyślnie `next_open`)

| Wejście | Zlecenie po sygnale na świecy t | Stop i cel liczone od |
| --- | --- | --- |
| `next_open` | Zlecenie rynkowe na otwarcie świecy t+1. | Zamknięcia świecy sygnału. |
| `stop` | Kup powyżej maksimum świecy t o `offset_atr` × ATR (dla short: sprzedaj poniżej minimum). Ważne `valid_bars` świec. | Poziomu zlecenia. |
| `limit` | Kup poniżej zamknięcia świecy t o `offset_atr` × ATR (dla short: sprzedaj powyżej). Ważne `valid_bars` świec. | Poziomu zlecenia. |

Domyślne: `stop`: `offset_atr`=0, `valid_bars`=1; `limit`: `offset_atr`=0,5, `valid_bars`=1. Zlecenie, które nie wypełni się w terminie, jest anulowane.

Kiedy które? `next_open`: proste, zawsze wchodzi. `stop`: wejście dopiero po potwierdzeniu ruchu (klasyczne dla wybić). `limit`: wejście taniej po krótkim cofnięciu (klasyczne dla mean reversion), ale **pomija najsilniejsze ruchy**, które nie cofają się wcale.

### 8.3 Początkowy stop (zawsze włączony)

Stop jest o `atr_mult` × ATR od ceny odniesienia (domyślnie 2,0 × ATR(14)). Ten stop **wyznacza wielkość pozycji** (ryzykujesz `risk_pct` konta do stopu) i definiuje **1R**.

### 8.4 Reguły wyjścia (domyślnie `target` + `time`)

Możesz włączyć dowolnie wiele. Zamknie transakcję ta, która zadziała pierwsza; stopy dynamiczne działają razem, a obowiązuje **najciaśniejszy**.

| Wyjście | Zamyka transakcję | Parametry (domyślnie) | Po co |
| --- | --- | --- | --- |
| `target` | Zleceniem z limitem `target_r` R od ceny odniesienia. | `target_r`=2,0 | Realizacja zysku na z góry ustalonym poziomie. |
| `time` | Na otwarciu po `max_hold_bars` świecach od wejścia. | `max_hold_bars`=20 | Nie trzymaj w nieskończoność transakcji, która „nic nie robi”. |
| `trailing` | Stopem `atr_mult` × ATR poniżej najwyższego maksimum od wejścia (dla short odwrotnie). | `atr_mult`=3,0 | „Niech zyski rosną”: stop podąża za ceną i nigdy się nie cofa. |
| `channel` | Stopem na najniższym minimum z ostatnich `period` świec (dla short: najwyższym maksimum). | `period`=10 | Wyjście typu Turtle: gdy cena łamie kanał. |
| `breakeven` | Po osiągnięciu przez cenę `trigger_r` R zysku stop przesuwa się na `lock_r` R od ceny wejścia. | `trigger_r`=1,0, `lock_r`=0,0 | „Zabezpiecz transakcję”: po zysku 1R najwyżej wyjdziesz na zero. `lock_r` musi być mniejsze od `trigger_r`. |
| `rsi` | Na następnym otwarciu, gdy RSI(`period`) zamknie się na poziomie `level` lub wyżej (dla short: 100 − `level` lub niżej). | `period`=2, `level`=70 | Wyjście dla mean reversion: odbicie się dokonało. |
| `sma_revert` | Na następnym otwarciu, gdy zamknięcie jest nad SMA(`period`) (dla short pod nią). | `period`=5 | Wyjście dla mean reversion: cena wróciła do średniej. |
| `sma_trend` | Na następnym otwarciu, gdy zamknięcie spada **pod** SMA(`period`) (dla short ponad nią). | `period`=50 | Wyjście dla trendu: trend został złamany. |
| `supertrend` | Na następnym otwarciu, gdy Supertrend wskazuje przeciw transakcji. | `period`=10, `mult`=3,0 | Wyjście dla trendu oparte na zmienności. |
| `failed_breakout` | Na następnym otwarciu, gdy któreś z pierwszych `within_bars` zamknięć jest niżej niż poziom wejścia o więcej niż `buffer_atr` × ATR. | `buffer_atr`=0,5, `within_bars`=5 | Wybicie, które się cofnęło, to fałszywe wybicie: wychodzisz szybko. |
| `no_progress` | Na następnym otwarciu, jeśli po `after_bars` świecach zysk jest mniejszy niż `min_r` R. | `after_bars`=5, `min_r`=0,5 | Transakcja, która „stoi w miejscu”, zajmuje kapitał: uwolnij go. |

**Parowanie z filozofią sygnału** (propozycje, nie zasady):

- Wybicia i trend: `trailing` / `channel` / `supertrend` + `failed_breakout` + `no_progress`.
- Mean reversion: `target` + `time` albo `rsi` / `sma_revert`.

**Zasady wykonania (ważne dla zrozumienia wyników):**

- Zlecenia wyjścia są zakładane na świecy wejścia, a sprawdzane od następnej.
- Gdy jedna świeca dotyka i stopu, i celu, **wygrywa stop**; dzienne świece nie pokazują, co stało się pierwsze, więc program przyjmuje scenariusz gorszy.
- Luka przez poziom wypełnia się po cenie otwarcia (a nie po cenie poziomu).
- Poślizg nigdy nie przesuwa transakcji poza zakres świecy, a zlecenie z limitem nie wypełnia się gorzej niż po limicie.
- Wyjście „na otwarciu” ma pierwszeństwo przed stopem i celem tej samej świecy.
- Sygnały są ignorowane, gdy czeka zlecenie lub otwarta jest pozycja.
- Trailing, channel i breakeven ustawiane są na zamknięciu dla następnej świecy i **tylko się zaciskają**.

Powód zamknięcia każdej transakcji jest zapisany: `stop`, nazwa reguły (`target`, `time`, `trailing`, …) albo `open` (wciąż otwarta na ostatniej świecy).

### 8.5 Pyramiding — dokupowanie do wygranej

Domyślnie wyłączony (`max_units` = 1). Gdy ustawisz `max_units` > 1, pozycja, która idzie po Twojej myśli, **dostaje kolejne jednostki** (styl Turtle):

- po wypełnieniu pierwszej jednostki na każdej kolejnej świecy czeka zlecenie stop na dokupienie, `add_every_atr` × ATR (domyślnie 0,5) za ceną poprzedniej jednostki; do `max_units` jednostek łącznie;
- ATR jest ze świecy sygnału, więc jednostki są równo rozmieszczone;
- każda dokupiona jednostka ma wielkość pierwszej; `max_position_pct` ogranicza każdą jednostkę z osobna, a nie całą pozycję;
- po dokupieniu stop **całej pozycji** przesuwa się na `atr_mult` ATR od ceny tego dokupienia;
- reguły wyjścia zamykają całość i liczą od pierwszej jednostki;
- „transakcja” to cała pozycja: data wejścia = pierwsza jednostka, cena wejścia = średnia, a R liczone jest w jednostkach ryzyka **jednej** jednostki, więc 1R to ta sama strata z pyramidingiem i bez niego;
- na świecy, na której pozycja wychodzi, nic się nie dokupuje.

Oba silniki dokupują tak samo. **Uwaga:** żaden nie odmówi wypełnienia z braku gotówki, więc kilka jednostek może być warte więcej niż konto. Pyramiding działa w Backtest, Sweep, Walk-forward i Watchlist, **nie działa** w Portfolio ani w Rotation (backtest portfela z `max_units` > 1 jest odrzucany; patrz [rozdział 16](#16-planowane-i-w-przygotowaniu)).

**Przykład.** `donchian_breakout` na `QQQ`, wyjście `trailing`, `--max-units 4 --add-every-atr 0.5`. W trendzie wzrostowym pozycja rośnie do czterech jednostek, a stop całości podąża za ostatnim dokupieniem. W trendzie bocznym zostaje przy jednej jednostce i strata jest taka sama jak bez pyramidingu. Pyramiding **zwiększa** zarówno zyski w trendach, jak i obsunięcia przy zwrotach, a Compare pokaże ten kompromis.

### 8.6 Koszty

Prowizja (`commission_pct`, domyślnie 0,1%) i poślizg (`slippage_pct`, domyślnie 0,05%) są procentami wartości transakcji. **Zawsze je uwzględniaj**: strategia, która „zarabia” tylko bez kosztów, nie zarabia.

---

## 9. Jak czytać wyniki i nie dać się oszukać

Największe ryzyko w testowaniu strategii to nie błąd programu, tylko **samooszukiwanie**: wyniki wyglądają świetnie, bo strategia dopasowała się do przeszłości. Program ma kilka narzędzi, które to utrudniają. Używaj ich.

### 9.1 In-sample i out-of-sample

Każdy backtest raportuje metryki dla dwóch okresów, podzielonych wg `backtest.oos_pct` (domyślnie **30%** historii od końca):

- **in-sample:** silnik dostaje tylko świece sprzed podziału, więc nic z późniejszego okresu nie może wpłynąć na wynik;
- **out-of-sample:** silnik dostaje całą historię (wskaźniki są „rozgrzane”), ale sygnał może zadziałać dopiero od punktu podziału; okres startuje ze świeżym kapitałem.

Każdy okres potrzebuje co najmniej 60 świec; przy krótszej historii podziału nie ma.

**Jak z tego korzystać:** stroisz na in-sample, a out-of-sample traktujesz jak egzamin. Ustawienie, które działa tylko in-sample, jest dopasowane do przeszłości.

**Pułapka:** jeśli po każdej zmianie zaglądasz w out-of-sample i poprawiasz, **zamieniasz je powoli w in-sample**. Egzamin zdany po trzydziestej próbie niczego nie dowodzi.

### 9.2 Liczba transakcji

- Poniżej ok. 20 transakcji: głównie szum.
- 30–100: wstępne wskazówki.
- 100+: dopiero wtedy statystyki zaczynają mieć sens.

Program oznacza przebiegi z mniej niż 20 transakcjami.

### 9.3 Plateau, a nie szczyt

W Sweep szukaj **szerokiego** obszaru dobrych wyników (a w oknie szczegółów porównaj komórkę ze **średnią jej sąsiadów**). Dobre ustawienie, którego sąsiedzi są słabe, to przypadek.

### 9.4 Szerokość

Wynik na jednym instrumencie to anegdota. Sprawdź Watchlist: czy działa na większości, czy trzymają go wyjątki. Z kolei wynik, który jest dodatni na 80% instrumentów, jest o wiele bardziej wiarygodny.

### 9.5 Monte Carlo

Pokazuje, jak bardzo wynik zależał od kolejności transakcji. Jeśli „pechowy” wariant (5. percentyl) jest nie do zniesienia dla Ciebie, to strategia jest dla Ciebie za ryzykowna, **nawet jeśli średnio zarabia**. Pamiętaj: model nie uwzględnia limitu wartości pozycji ani transakcji otwartej na końcu, więc jego liczby różnią się od liczb backtestu.

### 9.6 Walk-forward

Najuczciwszy test ustawień: strojenie na starszym kawałku, handel na nowszym, powtarzane. Jeśli **efficiency** jest niska, a wybierane ustawienia skaczą, to „najlepsze ustawienie” nie istnieje: istnieje tylko szum.

### 9.7 Dwa silniki

Jeśli `vectorized` i `cerebro` dają te same transakcje, to znak, że kod liczy poprawnie. Rozbieżność = coś jest nie tak (zgłoś błąd).

### 9.8 Lista kontrolna przed zaufaniem strategii

- [ ] Co najmniej 30 transakcji (najlepiej 100+).
- [ ] Out-of-sample też dodatnie, i bez „dostrajania pod” out-of-sample.
- [ ] Plateau w Sweep, a nie pojedynczy szczyt.
- [ ] Działa na większości instrumentów listy.
- [ ] Walk-forward efficiency blisko 1 (a nie 0,2).
- [ ] Koszty uwzględnione.
- [ ] Max drawdown (także „pechowy” z Monte Carlo) jest dla Ciebie do zniesienia.
- [ ] Wynik bije buy & hold albo ma wyraźnie mniejsze obsunięcie.
- [ ] Rozumiesz **dlaczego** reguła miałaby działać (nie tylko „że działała”).

> **Każde regulowane ustawienie to też sposób na dopasowanie do przeszłości.** Porównuj warianty na długiej historii i wielu instrumentach, nie ufaj ustawieniom, które działają tylko w wąskim przedziale, a mapy cieplne w Sweep pokazują i jedno, i drugie.

---

## 10. Konfiguracja: settings.toml i listy obserwowanych

### 10.1 Plik `config/settings.toml`

Zawiera **wartości domyślne** ustawień, na które nie trzeba się decydować przy każdym teście. Każdy klucz jest opcjonalny: brak klucza = wartość wbudowana. **Nieznane klucze i wartości spoza dozwolonego zakresu są odrzucane** z komunikatem, a nie ignorowane po cichu (dzięki temu literówka nie zmieni wyników bez Twojej wiedzy).

Edytujesz go zwykłym notatnikiem. Zmiany działają po ponownym uruchomieniu `tradescan serve` (CLI czyta plik przy każdym uruchomieniu).

| Sekcja | Co ustawia | Najważniejsze klucze (domyślnie) |
| --- | --- | --- |
| `[data]` | Skąd i jak długo pobierać dane. | `period`="5y" (dla scan i market), `interval`="1d", `cache_dir`=".cache", `cache_ttl_hours`=12 |
| `[account]` | Twoje konto. | `equity`=100000, `risk_pct`=1,0, `max_position_pct`=25,0, `lot_size`=1 |
| `[risk]` | Stop i cele. | `atr_period`=14, `atr_mult`=2,0, `targets_r`=[2,0; 3,0] |
| `[scan]` | Zachowanie Scannera. | `fresh_bars`=3, `min_score`=1,0, `benchmark`="SPY", `edge_horizon`=10, `min_bars`=60 |
| `[scoring]` | Premie punktacji. | `trend_bonus`=1,0, `weekly_bonus`=1,0, `rs_bonus`=1,0, `rs_strong_pct`=80 |
| `[scoring.family_weights]` | Waga rodzin sygnałów. | trend 1,0; momentum 1,0; breakout 1,5; mean_reversion 1,0; volume 1,0; pattern 0,5 |
| `[scoring.signal_weights]` | Wagi pojedynczych sygnałów (nadpisują wagi rodzin). | np. `golden_cross = 2.0` |
| `[trend]` | Definicje trendu i siły względnej. | `fast_period`=50, `slow_period`=200, `weekly_period`=30, `rs_periods`=[63,126,189,252], `rs_weights`=[0,4; 0,2; 0,2; 0,2] |
| `[regime]` | Ocena rynku (risk-on / risk-off). | `fast_period`=50, `slow_period`=200, `high_low_period`=252, `risk_on_breadth`=60, `risk_off_breadth`=40 |
| `[backtest]` | Historia i koszty testów. | `period`="10y", `commission_pct`=0,1, `slippage_pct`=0,05, `bars_per_year`=252, `oos_pct`=30 |
| `[pyramid]` | Dokupowanie. | `max_units`=1 (wyłączone), `add_every_atr`=0,5 |
| `[monte_carlo]` | Symulacje. | `simulations`=1000, `ruin_drawdown_pct`=50, `seed`=0 |
| `[portfolio]` | Limity portfela. | `max_positions`=10, `max_exposure_pct`=100 |
| `[rotation]` | Rotacja. | `holdings`=5, `absolute_lookback`=252 |
| `[walk_forward]` | Walk-forward. | `windows`=5, `in_sample_ratio`=3,0, `min_trades`=10 |

**Przykład: chcę ryzykować 0,5% zamiast 1% i mieć szerszy stop.**

```toml
[account]
risk_pct = 0.5

[risk]
atr_mult = 2.5
```

**Przykład: chcę, żeby `golden_cross` liczył się podwójnie w punktacji.**

```toml
[scoring.signal_weights]
golden_cross = 2.0
```

**Zasada podziału:** `settings.toml` trzyma wartości domyślne **ustawień**; domyślne wartości **parametrów sygnałów i reguł** (okresy, progi) są w kodzie. Pojedynczy przebieg może nadpisać dowolną z nich bez ruszania pliku: w interfejsie (zmienione pola są podświetlone), w API albo flagą w CLI.

### 10.2 Każdy parametr jest parametrem „deklarowanym”

Każda liczba, która zmienia wynik, ma: **wartość domyślną, dozwolony zakres i etykietę**. Dotyczy to wszystkich 38 sygnałów, filtrów, wejść, wyjść oraz sekcji `account`, `risk`, `scan`, `scoring`, `trend`, `regime`, `backtest`, `pyramid`, `monte_carlo`, `portfolio` i `rotation`. Wartość spoza zakresu, nieznana nazwa lub coś, co nie jest parametrem (np. ścieżki, ustawienia pamięci podręcznej), zostaje odrzucone. Dzięki temu możesz **wszystko porównywać w przeglądarce**, a opisy sygnałów (np. „RSI(3) < 15”) zawsze odpowiadają temu, co faktycznie policzono.

### 10.3 Listy obserwowanych (watchlisty)

To zwykłe pliki tekstowe w `config/watchlists/`: tickery oddzielone spacjami lub przecinkami, komentarze zaczynają się od `#`. Linia `# benchmark: SPY` ustawia **benchmark listy** (używany w filtrze „rynek”, w banerze reżimu i jako buy & hold w Portfolio/Rotation).

Dołączone listy:

| Lista | Zawartość | Benchmark |
| --- | --- | --- |
| `sp500` | 503 spółki z indeksu S&P 500 | SPY |
| `nasdaq100` | 101 spółek z Nasdaq-100 | QQQ |
| `us_large` | Duże spółki amerykańskie | (domyślny) |
| `etf` | Szerokie ETF-y rynkowe, klas aktywów i sektorowe (`SPY QQQ IWM … XLE XLF …`) | SPY |
| `wig20` | Próbka spółek WIG20 (symbole `.WA`); sprawdź aktualny skład indeksu | ETFBW20TR.WA |
| `crypto` | Duże pary kryptowalutowe; używaj `--lot-size 0.0001` | BTC-USD |

**Własna lista:** utwórz plik, np. `config/watchlists/moja.txt`:

```text
# Moje spółki
# benchmark: SPY
AAPL MSFT NVDA
PKO.WA
```

i wybierz `moja` w polu **Universe** (albo `-w moja` w CLI). Możesz też podać ścieżkę do pliku lub wpisać tickery bezpośrednio (**Tickers**, symbole Yahoo, np. `AAPL, PKO.WA, BTC-USD`).

**Uwaga o WIG20:** Yahoo nie ma historii samego indeksu WIG20, dlatego benchmarkiem jest ETF `ETFBW20TR.WA`.

### 10.4 Aktualizacja składu indeksów

Listy `sp500` i `nasdaq100` są generowane z Wikipedii; nagłówek pliku podaje źródło i datę. Odśwież je poleceniem `tradescan update-universes` (zob. [scenariusz F](#scenariusz-f-aktualizuję-listy-indeksów)). Opcja `--only sp500` odświeży tylko jedną.

**Wydajność:** listy od 40 instrumentów są przetwarzane na wszystkich rdzeniach procesora. Na 4 rdzeniach skan S&P 500 trwa ok. 30 s, a tabela edge z 10 lat ok. 35 s (przy danych w pamięci podręcznej); pierwsze uruchomienie pobiera wszystko i trwa 1–2 minuty. Dane są trzymane per instrument, więc `nasdaq100` korzysta z tego, co pobrał `sp500`.

---

## 11. Wiersz poleceń (CLI)

Interfejs w przeglądarce to nakładka. Wszystko to samo da się zrobić z terminala, np. do automatyzacji czy skryptów. **Uruchamiaj polecenia z folderu projektu** (albo podaj `--config` i `--watchlists-dir`).

### 11.1 Przegląd poleceń

| Polecenie | Co robi |
| --- | --- |
| `scan` | Sygnały z ostatnich `--fresh` świec, z punktacją, stopem, celem, rozmiarem i edge. |
| `market` | Ocena reżimu rynku (risk-on / neutral / risk-off). |
| `edge` | Statystyki przewagi sygnałów dla całej listy. |
| `backtest` | Jeden sygnał na jednym instrumencie, 1 lub 2 silniki, metryki in-sample/out-of-sample. |
| `sweep` | Backtest po 1–2 parametrach, siatki wyników in-sample/out-of-sample. |
| `walk-forward` | Strojenie i handel na kolejnych oknach historii. |
| `watchlist-backtest` | Ten sam setup na każdym instrumencie listy. |
| `portfolio-backtest` | Setup na całej liście ze wspólnym kapitałem i limitami. |
| `rotation-backtest` | Rotacja momentum. |
| `list-signals` | Katalog 38 sygnałów. |
| `update-universes` | Odświeżenie list `sp500` i `nasdaq100`. |
| `serve` | Interfejs WWW i API. |

Pomoc do każdego polecenia: `tradescan <polecenie> --help`.

### 11.2 Wspólne opcje

| Opcja | Znaczenie |
| --- | --- |
| `-w LISTA` / `-t TICKERY` | Lista z `config/watchlists/` (lub ścieżka do pliku) albo tickery po przecinku, np. `AAPL,MSFT,PKO.WA`. |
| `--period` | Okres historii Yahoo (np. `1y`, `5y`, `max`). |
| `--interval` | Interwał świec (domyślnie `1d`). |
| `--no-cache` | Zawsze pobieraj świeże dane. |
| `--equity`, `--risk-pct`, `--lot-size` | Konto, ryzyko na transakcję, krok zlecenia. |
| `--export plik.csv` (lub `.json`) | Zapis wyników do pliku. |

### 11.3 Przykłady z objaśnieniami

**Scan**

```bash
tradescan scan -w sp500 --min-score 4
```
Skan S&P 500, pokaż tylko propozycje z wynikiem co najmniej 4.

```bash
tradescan scan -w wig20 --direction long --top 10
```
Spółki WIG20, tylko long, 10 najlepszych.

```bash
tradescan scan -t AAPL,MSFT,PKO.WA --fresh 1 --export exports/hits.csv
```
Trzy wskazane tickery, tylko sygnały z ostatniej świecy, wynik zapisany do CSV.

```bash
tradescan scan -w crypto --lot-size 0.0001
```
Krypto z ułamkowymi wielkościami zleceń.

Dodatkowe opcje: `--signals` (które sygnały), `--family` (rodziny: `trend, momentum, breakout, mean_reversion, volume, pattern`), `--direction long|short|both`, `--benchmark`, `--top`.

**Market**

```bash
tradescan market -w us_large
```
Ocena reżimu na podstawie benchmarku i szerokości listy.

**Edge**

```bash
tradescan edge -w etf --family breakout,trend --min-events 30
```
Przewaga sygnałów z rodzin breakout i trend na ETF-ach; ukryj sygnały z mniej niż 30 zdarzeniami. Opcje: `--horizons 5,10,20` (po ilu świecach mierzyć).

**Backtest**

```bash
tradescan backtest SPY donchian_breakout --engine both
```
Wybicie Donchiana na SPY w obu silnikach.

```bash
tradescan backtest SPY connors_rsi2_long --entry limit --exits time --max-hold 5
```
Wejście zleceniem z limitem, wyjście tylko czasowe po 5 świecach (plus stop początkowy).

```bash
tradescan backtest QQQ donchian_breakout --exits trailing,breakeven
```
Wyjścia: trailing stop i przesunięcie na breakeven.

```bash
tradescan backtest QQQ donchian_breakout --exits trailing --max-units 4 --add-every-atr 0.5 --engine both
```
Pyramiding do 4 jednostek.

```bash
tradescan backtest SPY connors_rsi2_long --exits rsi,time --engine both
```
Wyjścia na RSI i po czasie.

```bash
tradescan backtest QQQ donchian_breakout --entry stop --exits failed_breakout,no_progress,trailing
```
Wejście zleceniem stop plus wyjścia „nieudane wybicie”, „brak postępu” i trailing.

```bash
tradescan backtest AAPL donchian_breakout --filters trend,market,volume --benchmark QQQ
```
Trzy filtry wejścia; filtr rynku porównuje QQQ.

```bash
tradescan backtest SPY connors_rsi2_long --oos 20
```
Out-of-sample = ostatnie 20% historii (dozwolone 10–50).

Pozostałe opcje: `--atr-mult`, `--target-r`, `--max-hold`, `--commission-pct`, `--slippage-pct`, `--trades` (ile ostatnich transakcji pokazać), `--export`. `--exits none` zostawia tylko stop początkowy; domyślnie `target,time`.

**Sweep**

```bash
tradescan sweep SPY connors_rsi2_long --axis signal.oversold=4:16:2 --axis exit.target.target_r=1,2,3 --metric expectancy_r
```
Siatka: `oversold` od 4 do 16 co 2 (7 wartości) razy 3 cele (1R, 2R, 3R) = 21 kombinacji. Opcja `--axis` ma postać `cel[.właściciel].nazwa=OD:DO:KROK` lub `=W1,W2,…`; cel to `signal`, `entry`, `exit` (właściciel: reguła wyjścia), `filter` (właściciel: filtr) albo `settings` (właściciel: `account`, `risk`, `backtest` lub `pyramid`). Podaj ją dwa razy, by dostać siatkę. `--metric` wybiera metrykę kolorującą mapy: `total_return_pct`, `cagr_pct`, `sharpe`, `sortino`, `max_drawdown_pct`, `trades`, `win_rate_pct`, `profit_factor`, `expectancy_r`, `sqn`, `exposure_pct`, `buy_hold_pct`. `--export` zapisuje każdą kombinację.

**Walk-forward**

```bash
tradescan walk-forward SPY connors_rsi2_long --axis signal.oversold=5:25:2.5 --axis exit.target.target_r=1:3:0.5 --windows 5
```
Strojenie dwóch parametrów na 5 oknach. Dodatkowe opcje: `--in-sample-ratio` (domyślnie 3), `--scheme rolling|anchored`, `--min-trades` (domyślnie 10), `--metric` (wg czego okno wybiera), `--trades`, `--export`.

**Watchlist-backtest**

```bash
tradescan watchlist-backtest connors_rsi2_long -w etf --filters market --metric expectancy_r
```
Ten sam setup na każdym ETF-ie; wyświetla `--top` najlepszych instrumentów wg metryki, rozrzut metryki i zebrane transakcje.

**Portfolio-backtest**

```bash
tradescan portfolio-backtest donchian_breakout -w sp500 --filters trend --max-positions 10 --priority momentum
```
Portfel na S&P 500: filtr trendu, maksymalnie 10 pozycji, priorytet momentum. Opcje: `--max-exposure` (% kapitału), `--priority` (`relative_strength`, `momentum`, `score`; `score` czyta `[scoring]`, `[trend]` i `[scan] fresh_bars` z ustawień), `--engine` (`vectorized`, `cerebro`, `both`), `--top`, `--export`. Bez pyramidingu.

**Rotation-backtest**

```bash
tradescan rotation-backtest -w etf --holdings 3 --weighting inverse_volatility --safe-asset TLT
```
Rotacja na ETF-ach: 3 pozycje, wagi odwrotnie do zmienności, `TLT` jako bezpieczne aktywo. Opcje: `--rank momentum|relative_strength`, `--rebalance weekly|monthly`, `--weighting equal|inverse_volatility`, `--absolute-lookback` (0 wyłącza), `--benchmark`, `--engine`, `--top` (0: wszystkie), `--oos`, `--export`. Wypisuje też, co wybrałby rebalans na ostatnim zamknięciu.

**List-signals / update-universes / serve**

```bash
tradescan list-signals
tradescan update-universes --only sp500
tradescan serve --port 9000 --db moje.db
```

### 11.4 Kiedy CLI, a kiedy przeglądarka

- **Przeglądarka:** gdy chcesz oglądać wykresy, klikać w wyniki, przypinać i porównywać, prowadzić dziennik.
- **CLI:** gdy chcesz szybko uruchomić pojedynczy test, zautomatyzować (zadanie harmonogramu: codzienny skan i zapis do CSV) albo wyeksportować dane do arkusza.

---

## 12. Dane, zapis i kopie zapasowe

### 12.1 Skąd są dane

Ceny pobierane są z **Yahoo Finance** (biblioteka `yfinance`) i zapisywane lokalnie w formacie Parquet w folderze `.cache/`, ważne `cache_ttl_hours` godzin (domyślnie 12). Po upływie tego czasu (albo z `--no-cache`) dane są pobierane na nowo.

**Uwaga:** Yahoo to nieoficjalne źródło. Zdarzają się limity zapytań i zmiany formatu; do użytku osobistego zgodnie z warunkami Yahoo.

### 12.2 Co zapisuje serwer

Przypięte przebiegi i dziennik transakcji trafiają do **jednego pliku SQLite**: `tradescan.db` w folderze, z którego uruchomiono `serve` (`--db ŚCIEŻKA` wybiera inny). Dlatego każda przeglądarka na tym komputerze widzi te same przebiegi i transakcje.

| Co | Gdzie |
| --- | --- |
| Pobrane ceny | `.cache/` (można skasować; pobiorą się znowu) |
| Przypięte przebiegi i dziennik | `tradescan.db` |
| Ustawienia konta (wielkość, ryzyko) | Przeglądarka (per przeglądarka) |
| Domyślne wartości ustawień | `config/settings.toml` |
| Listy | `config/watchlists/*.txt` |

### 12.3 Kopia zapasowa

- **Dziennik i przypięte przebiegi:** skopiuj `tradescan.db` **przy zatrzymanym serwerze** (inaczej plik może być w trakcie zapisu).
- **Samo przypięte przebiegi:** w Compare **Export JSON** zapisuje je do pliku, a **Import JSON** je przywraca. Dziennik nie wchodzi do tego eksportu.
- Jeśli wcześniej (w starszych wersjach) przebiegi były w przeglądarce, **przeniosą się na serwer przy pierwszym otwarciu interfejsu w tej przeglądarce**. Te, które nie mieszczą się obok już zapisanych (limit 8), zostają w przeglądarce, dopóki nie zwolni się miejsce, i trafią na serwer po odświeżeniu strony.
- Transakcja w dzienniku trzyma własną kopię przebiegu, który ją podpowiedział, więc odpięcie przebiegu nie zmienia transakcji.

### 12.4 Limity

- Do **8** przypiętych przebiegów naraz.
- Sweep: do 200 kombinacji, 2–50 wartości na parametr.
- Walk-forward: do 2000 backtestów, 2–20 okien.
- Historia podziału in/out-of-sample: co najmniej 60 świec na okres.

---

## 13. Bezpieczeństwo

- **API nie ma uwierzytelniania.** `serve` domyślnie nasłuchuje tylko na `127.0.0.1`, czyli jest dostępny wyłącznie z Twojego komputera. **Nie wystawiaj go do sieci** (nie ustawiaj `--host 0.0.0.0` w sieci, której nie ufasz), tym bardziej że **dziennik zawiera Twoje prawdziwe transakcje**.
- Serwer odpowiada tylko na żądania adresowane do `localhost`, `127.0.0.1`, `[::1]` lub do wartości `--host`, a pozostałe odrzuca kodem 400. Dzięki temu zwykła strona WWW otwarta w innej karcie nie może się do niego dobrać przez tzw. DNS rebinding.
- Program **niczego nie wysyła** poza zapytaniami o ceny do Yahoo i (opcjonalnie) o składy indeksów do Wikipedii. Nie ma konta, telemetrii ani chmury.
- Program **nie ma dostępu do Twojego domu maklerskiego** i nie składa zleceń.

---

## 14. Ograniczenia, o których musisz wiedzieć

1. **Ostatnia świeca jeszcze się tworzy podczas sesji.** Skanuj po zamknięciu rynku.
2. **Błąd przetrwania (survivorship bias).** Dołączone listy zawierają **dzisiejszych** członków indeksów. Spółki, które wypadły z S&P 500 lub Nasdaq-100 (często dlatego, że szły słabo), nie występują w statystykach, więc wyniki historyczne są nieco zawyżone.
3. **Dzienne świece nie pokazują kolejności zdarzeń wewnątrz dnia.** Jeśli jedna świeca dotknęła i stopu, i celu, program zakłada, że wygrał **stop**. To założenie pesymistyczne, ale bezpieczne.
4. **Yahoo to nieoficjalne źródło.** Limity i zmiany formatu mogą zakłócić pobieranie. Indeks WIG20 nie ma historii na Yahoo.
5. **backtrader (Cerebro) nie jest już rozwijany** (ostatnie wydanie 2023). Działa tu z Pythonem 3.13, pandas 3 i numpy 2, ale jego własne wykresy nie są używane. Cerebro jest silnikiem referencyjnym i bywa wolny (ok. minuty na 20 instrumentów z 10 lat w portfelu i rotacji).
6. **Portfel i rotacja nie dokupują (brak pyramidingu).**
7. **Broker w symulacji nigdy nie odmawia z braku gotówki** (w portfelu limit ekspozycji jest jedynym ograniczeniem); luka może więc wypełnić pozycję nieco ponad limit.
8. **Gotówka nie jest oprocentowana** (rotacja).
9. **Przeszłość nie gwarantuje przyszłości.** Każdy wynik to statystyka historyczna.
10. **Brak podatków i realiów konkretnego brokera:** nie ma podatków, minimalnych prowizji, ograniczeń krótkiej sprzedaży ani kosztów pożyczki akcji (przy short).

---

## 15. Najczęstsze pytania i problemy

**`tradescan` nie jest rozpoznawane jako polecenie.**
Uruchamiaj je ze środowiska wirtualnego: `.venv\Scripts\tradescan serve` albo aktywuj środowisko (`.venv\Scripts\activate`).

**Interfejs się nie otwiera / widzę pustą stronę lub błąd o braku plików.**
Nie zbudowałeś interfejsu. Wykonaj `npm --prefix frontend install` i `npm --prefix frontend run build`, potem `tradescan serve` ponownie.

**Port 8000 jest zajęty.**
`tradescan serve --port 9000`.

**Pierwszy skan trwa bardzo długo.**
To normalne: pobierane są dane każdego instrumentu (1–2 minuty dla S&P 500). Kolejne skany używają pamięci podręcznej.

**Dane wyglądają na nieaktualne.**
Pamięć podręczna jest ważna 12 godzin. Użyj `--no-cache` (CLI lub `serve`) albo skasuj folder `.cache/`.

**`--engine cerebro` nie działa.**
Zainstaluj dodatek: `.venv\Scripts\python -m pip install -e ".[cerebro]"`.

**Dla niektórych instrumentów brak wyników albo „za mało historii”.**
Instrument ma mniej niż 60 świec (Scanner pomija takie) albo zbyt krótką historię na wskaźniki. Wydłuż okres (`History`, `--period`).

**Instrument z wolumenem wcale nie przechodzi filtra `volume`.**
Instrumenty bez wolumenu (indeksy, część walut) nigdy go nie przejdą. Użyj innego filtra.

**Tickery z mojej giełdy nie działają.**
Używaj symboli Yahoo: np. `PKO.WA` (Warszawa), `BRK-B` (z myślnikiem), `BTC-USD`.

**Dostaję błąd o wartości spoza zakresu.**
To zamierzone: program odrzuca wartości spoza dozwolonego zakresu i nieznane klucze, zamiast liczyć po cichu coś innego. Zakres każdego parametru zobaczysz w **Signals** i przy polach formularza.

**Dlaczego dwa silniki dają nieco inne wyniki?**
Nie powinny dawać innych transakcji. Jeśli dają, to błąd; zgłoś go z opisem setupu (najlepiej linkiem z paska adresu).

**Wynik jest świetny, ale boję się, że to przypadek.**
Przejdź listę kontrolną z [rozdziału 9.8](#98-lista-kontrolna-przed-zaufaniem-strategii).

**Czy mogę automatycznie handlować?**
Nie. Program niczego nie kupuje ani nie sprzedaje.

**Czy mogę używać go na akcjach polskich?**
Tak, symbole `.WA`. Pamiętaj o benchmarku (np. ETF `ETFBW20TR.WA` zamiast indeksu) i o tym, że lista `wig20` to próbka do weryfikacji.

---

## 16. Planowane i w przygotowaniu

Plan rozwoju (plik `ROADMAP.md`) mówi, że **wszystkie zaplanowane wcześniej pozycje są zrobione**: parametry w interfejsie, porównywanie przebiegów, reguły wejścia i wyjścia, sweep i podział out-of-sample, stopy dynamiczne, wyjścia wskaźnikowe i wybiciowe, filtry wejścia, sygnały mean reversion, backtest listy, Monte Carlo, portfel, rotacja, pyramiding, walk-forward oraz dziennik z zapisem na serwerze. Przypinanie i porównywanie przebiegów rotacji, które zostało zrobione jako ostatnie, jest opisane wyżej w rozdziałach [Rotation](#57-rotation--trzymaj-najsilniejszych) i [Compare](#59-compare--porównanie-przypiętych-wyników).

Poniżej to, co jest **zgłoszone jako następne kroki** (otwarte tickety w repozytorium) i **jeszcze nie działa w programie**. Opisuję je, żebyś wiedział, czego się spodziewać i czego na razie nie próbować.

### 16.1 Sweep dla rotacji (zgłoszenie #45)

**Czego brakuje dziś:** Sweep (mapy cieplne) działa tylko dla backtestu jednego instrumentu. Parametrów rotacji (liczba pozycji, okno momentum bezwzględnego, okna rankingu, okno ważenia odwrotną zmiennością, koszty) nie da się „przeskanować”. Ocena, czy ustawienie rotacji jest odporne, wymaga wielu ręcznych przebiegów i porównania ich w Compare.

**Co będzie:** Sweep rotacji z mapami cieplnymi in-sample i out-of-sample, tak jak dla backtestów. Pozwoli sprawdzić, czy np. „3 pozycje” to plateau czy przypadkowy szczyt.

**Jak radzić sobie teraz:** uruchamiaj rotację kilka razy ze zmienionym jednym parametrem, przypinaj każdy przebieg (**Pin run**) i porównuj w Compare; patrz [scenariusz C](#scenariusz-c-jaka-wersja-jest-lepsza).

### 16.2 Ranking rotacji wg wyniku zbieżności Scannera (zgłoszenie #46)

**Czego brakuje dziś:** rotacja szereguje instrumenty tylko regułami, które czytają same ceny: `momentum` i `relative_strength`. Reguła `score` (punktacja Scannera) jest odrzucana, bo wymaga sygnału i ustawień skanera.

**Co będzie:** możliwość rankingu rotacji wg wyniku zbieżności: świeże sygnały long, premie za trend i siłę względną. Rotacja trzymałaby wtedy instrumenty, które Scanner ocenia najwyżej. Na ekranie Rotation pojawią się odpowiednie ustawienia punktacji i parametry sygnałów, tak jak na ekranie Portfolio.

**Jak radzić sobie teraz:** ranking `momentum` lub `relative_strength`; wynik zbieżności możesz sprawdzać ręcznie w Scannerze.

### 16.3 Pyramiding w portfelu (zgłoszenie #50)

**Czego brakuje dziś:** backtest portfela odrzuca `max_units` > 1, a formularz Portfolio chowa pola pyramidingu.

**Dlaczego to nie jest proste:** dokupowanie w portfelu wymaga osobnego projektu zasad: czy dokupienie zajmuje „miejsce” w limicie pozycji, jak liczy się do limitu ekspozycji, co robić, gdy limit nie zostawia miejsca, i które zlecenia (dokupienia czy nowe sygnały) mają pierwszeństwo tego samego dnia. Oba silniki portfelowe (vectorized i Cerebro) musiałyby to robić tak samo.

**Jak radzić sobie teraz:** pyramiding sprawdzaj w Backtest, Sweep, Walk-forward i Watchlist (każdy instrument osobno).

### 16.4 Ponowne otwieranie przypiętego przebiegu a zmieniony `settings.toml` (zgłoszenie #66)

**Problem dziś (ważny, jeśli edytujesz `settings.toml`):** przypięty przebieg pamięta tylko te ustawienia, które **różniły się od domyślnych w dniu przypięcia**. Jeśli później zmienisz domyślne w `settings.toml` (np. `max_units` z 1 na 3), to **Open in Backtest / Open in Portfolio uruchomi inny setup niż ten, który przypięto**: przebieg z pyramidingiem wyłączonym otworzy się z włączonym. Dotyczy to też ryzyka, kosztów, konta i każdego innego ustawienia. Sekcja „config” przypiętego przebiegu pokazuje, co faktycznie liczono, więc wynik ponownego uruchomienia po cichu się różni od przypiętego.

**Co będzie:** ponownie otwarty formularz niesie **wszystkie ustawienia, których użyto w przebiegu** (z jego „config”), a nie tylko różnice względem dzisiejszych domyślnych.

**Jak radzić sobie teraz:** nie zmieniaj domyślnych w `settings.toml` między przypięciem a ponownym otwarciem. Jeśli musisz, porównuj na wykresie i w tabeli parametrów w Compare to, co liczono (przypięty wynik), a nie wynik ponownego uruchomienia.

### 16.5 Jedno wspólne pole wyboru silników (zgłoszenie #68)

**Co to jest:** porządki w kodzie interfejsu. Wybór silnika (`vectorized`, `cerebro`, oba) jest dziś skopiowany do trzech stron (Backtest, Portfolio, Rotation); zmiana (np. nowy silnik, etykieta, próg ostrzeżenia o wolnym Cerebro) musi być wprowadzana trzykrotnie, a kopie mogą się rozjeżdżać.

**Co zmieni się dla Ciebie:** nic widocznego. To zmiana wewnętrzna, która ma zapobiec niespójnościom w przyszłości.

### 16.6 Jak śledzić postępy

- Plik `ROADMAP.md` w repozytorium opisuje kierunek i status pozycji.
- Zgłoszenia (Issues) w repozytorium GitHub zawierają szczegóły każdej planowanej zmiany.

> Opisy z tego rozdziału wynikają ze zgłoszeń z dnia przygotowania dokumentu. Stan może się zmienić; sprawdź otwarte zgłoszenia, zanim zaplanujesz pracę wokół którejś z funkcji.

---

## 17. Dla programistów: jak rozszerzać program

Ten rozdział jest dla osób, które chcą dopisać własną funkcję. Jeśli nie programujesz, możesz go pominąć. Pełny opis techniczny jest w pliku `README.md`.

Kod trzyma się zasad SOLID: **każde rozszerzenie to nowa klasa, a nie edycja istniejącej logiki.**

| Chcesz dodać | Co zrobić |
| --- | --- |
| **Nowy sygnał** | Podklasa `Signal`, metoda `condition`, dekorator `@register`, import w `signals/__init__.py`. Każdą liczbę zadeklaruj przez `param(...)` i użyj w opisie (`description`), bo test tego wymaga. Scanner, punktacja, edge, oba silniki, CLI i interfejs odbiorą go automatycznie. |
| **Nowy filtr / wejście / wyjście** | Podklasa `EntryFilter` (`backtest/filters.py`), `EntryRule` (`backtest/entries.py`) lub `ExitRule` (`backtest/exits.py`); rejestracja `@entry_filters.register` / `@entry_rules.register` / `@exit_rules.register`. Test zgodności silników uruchomi nową regułę na obu silnikach. |
| **Nowa reguła rankingu lub ważenia (rotacja)** | `TickerPriorityRule` w `backtest/priority.py` lub `WeightRule` w `backtest/weighting.py`; rejestracja `@priority_rules.register` / `@weight_rules.register`. |
| **Nowe źródło danych** | Zaimplementuj protokół `DataProvider` (`history(tickers, period, interval)`); `CachedProvider` opakuje dowolne źródło. |
| **Nowy silnik backtestu** | Zaimplementuj `BacktestEngine.run` i dodaj do `default_engines()` w `services/composition.py`. |
| **Nowy format eksportu** | Dopisz funkcję zapisującą do `_WRITERS` w `report/export.py`. |
| **Nowy endpoint API** | Moduł w `api/routes/` z funkcją `build_router(context)` i wpis w `ROUTERS` w `api/app.py`. |
| **Nowe polecenie CLI** | Moduł w `cli/commands/` z obiektem `COMMAND`, wpis w `COMMANDS` w `cli/commands/__init__.py`. |
| **Nowe dane trwałe** | Nowy magazyn obok `PinnedRunStore` i `TradeJournal` w `storage/` oraz **nowa migracja** dopisana na końcu `_MIGRATIONS` w `storage/database.py` (nigdy nie edytuj istniejącej: pliki ze starszych wersji są z niej aktualizowane). |

Przypadki użycia (`services/`, po jednym module na funkcję) trzymają logikę; `cli/` i `api/` tylko tłumaczą wejście i wyjście.

### Testy i jakość

```bash
.venv\Scripts\python -m pytest
npm --prefix frontend test
npm --prefix frontend run typecheck
```

Testy Pythona działają na deterministycznych danych syntetycznych i **nigdy nie łączą się z siecią**; testy interfejsu mockują API. Jakość kodu sprawdzają: `ruff check .`, `ruff format --check .`, `mypy` (Python) oraz `npm --prefix frontend run lint` i `format:check`.

### Rozwój interfejsu

Uruchom równolegle API i serwer deweloperski Vite (przekazuje `/api` do API):

```bash
tradescan serve
npm --prefix frontend run dev
```

Po zmianie modeli API wygeneruj ponownie typy TypeScript:

```bash
python scripts/export_openapi.py frontend/openapi.json
npm --prefix frontend run gen:api
```

---

*Koniec instrukcji. Pytania, błędy i pomysły zgłaszaj jako Issues w repozytorium projektu.*
