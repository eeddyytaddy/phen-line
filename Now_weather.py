#爬蟲抓取現在的天氣

from openpyxl import Workbook , load_workbook
from selenium import webdriver
from selenium.webdriver.common.by import By #find_elements(By.)
from selenium.webdriver.chrome.options import Options
import time
import re
from opencc import OpenCC
import requests
from bs4 import BeautifulSoup



def weather():
    # 下載網頁內容
    response = requests.get("https://www.tianqi24.com/penghu.html")
    # 解析 HTML 內容
    soup = BeautifulSoup(response.text, "html.parser")

    #取得天氣
    result = soup.find("section")
    a = result.select("article")
    b = a[0].find("section")
    c = b.find("ul")
    d = c.select("li")
    e = d[1].select("div")
    cc = OpenCC('s2t')
    weather = cc.convert(e[2].text) 
    #print(weather)
    return weather
    
def temperature():
    # 下載網頁內容
    response = requests.get("https://www.tianqi24.com/penghu.html")
    # 解析 HTML 內容
    soup = BeautifulSoup(response.text, "html.parser")

    #取得氣溫
    result = soup.find("section")
    a = result.select("article")
    b = a[0].find("section")
    c = b.find("ul")
    d = c.select("li")
    e = d[1].select("div")
    numbers = re.findall('\d+',e[3].text) 
    temperature = int(numbers[0])
    #print(number)

    return temperature

def tidal():
    #取得現在時間
    localtime = time.localtime()
    local_time = int(localtime[3])*60+int(localtime[4])
    #print(local_time)

    range_hour = 60

    # 下載網頁內容
    response = requests.get("https://www.migrator.com.tw/tw/events/%E6%9C%AA%E4%BE%86%E4%B8%80%E5%80%8B%E6%9C%88%E6%BD%AE%E6%B1%90%E9%A0%90%E5%A0%B1.html")
    # 解析 HTML 內容
    soup = BeautifulSoup(response.text, "html.parser")

    #第一個滿潮/乾潮
    result = soup.find("table")
    a = result.select("tr")
    b1 = a[1].select("td")
    c1 = b1[2].text.split(':')
    high_min1 = int(c1[0])*60+int(c1[1])
    #print(high_min1)
    c2 = b1[3].text.split(':')
    low_min1 = int(c2[0])*60+int(c2[1])
    #print(low_min1)

    #判斷是否有兩個滿潮
    flag = b1[0].get("rowspan")
    #print(flag)
    if flag == '2' :
        b2 = a[2].select("td")
        c1 = b2[0].text.split(':')
        high_min2 = int(c1[0])*60+int(c1[1])
        #print(high_min2)
        c2 = b2[1].text.split(':')
        low_min2 = int(c2[0])*60+int(c2[1])
        #print(low_min2)
    else:
        high_min2 = high_min1
        low_min2 = low_min1
        
    #判斷潮位
    if (high_min1-range_hour < local_time and local_time < high_min1+range_hour) or (high_min2-range_hour < local_time and local_time < high_min2+range_hour):
        tidal = 2
    elif (low_min1-range_hour < local_time and local_time < low_min1+range_hour) or (low_min2-range_hour < local_time and local_time < low_min2+range_hour):
        tidal = 0
    else:
        tidal = 1
    #print(tidal)

    return tidal

    
#print(weather())  
#print(temperature())  
#print(tidal())