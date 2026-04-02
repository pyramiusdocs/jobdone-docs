# 單一資料夾權限

『資料夾權限』是指針對特定頂層資料夾內的文件進行精確的訪問控制。這項機制讓管理員能依據專案階段（如：發包期、施作期）、職能部門（如：土木、機電）或成員角色，靈活地調整文件的閱覽與操作範圍。


!!! info
    #### 補充說明
    
    * **預設繼承邏輯：**&#x8CC7;料夾的『預設權限』是依據專案全域文件權限。意即若未手動修改，成員在各資料夾的權限將與其全域設定一致。
    * **修改權限限制：**&#x70BA;確保管理體系之穩定，管理員僅能更動『非管理員』成員的權限。
    * ****頂層控管邏輯：****系統規定僅有『第一層資料夾（頂層資料夾）』能夠更改權限。一但完成設定，該資料夾下方的所有子資料夾均會同步套用。


### 01｜權限編輯流程

欲修改特定資料夾的權限，請執行以下步驟：

{% stepper %}
{% step %}
#### 選擇資料夾

在『所有檔案』頁面中，管理員可透過以下兩種方式靈活進入權限設定介面：

1. 直接於資料夾列表中，在目標資料夾右側點選 ![](https://2002560121-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FEqUCL3D5WQfpxJw8NL3P%2Fuploads%2FowOZiXzdooeCwaJmoy7W%2Fimage.png?alt=media\&token=35363eb3-31da-4f57-9ae2-f17e201719a0) 圖示，並選擇 ![](https://2002560121-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FEqUCL3D5WQfpxJw8NL3P%2Fuploads%2FPNH3H6wsZVwbcHo7zub8%2Fimage.png?alt=media\&token=2362c35f-2061-4e32-a348-5212adbcae72) 功能。
2. 先點選進入該資料夾，再點擊畫面右上方之 ![](https://2002560121-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FEqUCL3D5WQfpxJw8NL3P%2Fuploads%2FAdPGlHIj4yaYkdAzXpBg%2Fimage.png?alt=media\&token=61b6a84e-e488-4587-b9ef-0bd63f434765) 圖示，從選單中選取 ![](https://2002560121-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FEqUCL3D5WQfpxJw8NL3P%2Fuploads%2FPHLaWpSzwX9q8NkFa4F3%2Fimage.png?alt=media\&token=10cdeab8-6de5-46eb-9b77-b42163443cfe)。

無論採用哪種方式，皆可針對該第一層資料夾進行精確的成員權限調控。

> 頂層資料夾如下圖範例之：![](https://2002560121-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FEqUCL3D5WQfpxJw8NL3P%2Fuploads%2F2kN9ao2of5dowJvRID3a%2Fimage.png?alt=media\&token=203eeebb-3948-4830-9a84-1594a4e7de5d)**施工文件**、![](https://2002560121-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FEqUCL3D5WQfpxJw8NL3P%2Fuploads%2F8XBDI7MZtODm1nZkL9T5%2Fimage.png?alt=media\&token=e6fd9e83-9472-4fab-aec3-97a087ffa33c)**材料相關**

<div>![圖一 - 點選「⋮」](../../../../images/7a6570a352895c02.png) ![](../../../../images/df4796f86627d89a.png)</div>

權限設定畫面如下：

![圖三 - 開啟權限設定畫面](../../../../images/d40cf4df6eb52a64.png)
{% endstep %}

{% step %}
#### 編輯資料夾權限

開啟『設定權限』視窗後，只需點擊權限欄位即可展開選單，並從中選取欲賦予該成員的權限等級。

<div>![圖四 - 設定權限(一)](../../../../images/1ca07c7a9982c210.png) ![圖五 - 設定權限(二)](../../../../images/b841d7631bf2928d.png)</div>
{% endstep %}
{% endstepper %}
