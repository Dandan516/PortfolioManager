# Portfolio Manager

Portfolio Manager fetches the latest available prices for stock symbols listed in a text file. It opens as a desktop app on Windows. The app runs through WSL2 (the Windows Subsystem for Linux), which must be installed and enabled for Linux graphical apps.

## Setup (one time)

1. Clone from GitHub.

   ```powershell
   git clone https://github.com/Dandan516/PortfolioManager/
   ```

2. Open **PowerShell**.
3. Go to the Portfolio Manager folder. For example:

   ```powershell
   cd D:\PortfolioManager
   ```

4. If WSL2 is not installed yet, install Ubuntu by running:

   ```powershell
   wsl --install -d Ubuntu
   ```

   Follow any Windows prompts to finish installing Ubuntu. You only need to install WSL once.

5. In PowerShell, from the Portfolio Manager folder, prepare the app:

   ```powershell
   .\setup.ps1
   ```

   Setup installs the app's required software inside Ubuntu. It may take a few minutes the first time.

## Run the app

Whenever you want to use Portfolio Manager:

1. Open **PowerShell** and go to the Portfolio Manager folder:

   ```powershell
   cd D:\PortfolioManager
   ```

2. Start the app:

   ```powershell
   python main.py
   ```

3. The **Fetch Stock Prices** tab opens. The file path shown next to **Browse file** is the list of stock symbols the app will use.

## Fetch stock prices

1. Prepare a plain text file with **one stock symbol per line**, for example:

   ```text
   AAPL
   MSFT
   7203.T
   ```

   The project includes `stock_codes.txt` as a sample list. You can edit it with Notepad or another text editor.

2. To use a different list, click **Browse file** and select your `.txt` file. The selected file's Windows path appears next to the button.
3. Click **Fetch Prices** and wait for the status to change to **Done**.
4. The results appear in the table. The app also saves them to `stock_prices.xlsx` in the Portfolio Manager folder. Open that file with Excel to keep or share the results.

An internet connection is required to retrieve prices. A blank price means a price could not be retrieved for that symbol. Prices are the latest available from the data provider and may not be real-time.

## Other information

The **Contracts** tab is temporarily unavailable.

WSL can also be installed separately from the app. If you already have a different WSL distribution installed, choose it during setup with:

```powershell
.\setup.ps1 -Distribution Ubuntu-24.04
```
