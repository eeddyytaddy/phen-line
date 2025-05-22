#

from selenium import webdriver
from selenium.webdriver.common.by import By #find_elements(By.)
from selenium.webdriver.chrome.options import Options
import time
def Attractions_recommend(keyword):
    keyword = "澎湖" + keyword 
    #設定 chrome Driver 的執行檔路徑
    options = Options()
    options.chrome_executable_path = "C:/Users/roy88/chromedriver_win32/chromedriver.exe"
    #建立 Driver 物件實體，用程式操作瀏覽器運作
    driver = webdriver.Chrome(options = options)

    #地圖
    driver.get("https://www.google.com/maps?q=" + keyword)
    map_url = driver.current_url

    #圖片
    driver.get("https://www.google.com/search?q=" + keyword + "&tbm=isch")
    # 等待圖片加載完成
    driver.implicitly_wait(5)
    # 獲取第一張圖片的網址
    img_element = driver.find_element(By.XPATH,'//*[@id="islrg"]/div[1]/div[1]/a[1]/div[1]/img')
    img_element.click()
    img_element1 = img_element.find_element(By.XPATH,'//*[@id="islrg"]/div[1]/div[1]/a[1]')
    img_url = img_element1.get_attribute("href")

    driver.get(img_url)
    img_element2 = driver.find_element(By.XPATH,'//*[@id="imp"]/div/div[1]/div/div[2]/div[2]/div[2]/c-wiz/div/div/div/div[2]/div/a/img[1]')
    img_url = img_element2.get_attribute("src")


    #網頁
    driver.get("https://www.google.com/search?q=" + keyword)
    # 找到第一個網頁的元素，獲取圖片href
    link_element = driver.find_element(By.CSS_SELECTOR , "div#search div.g a")
    web_url = link_element.get_attribute("href")

    driver.quit()
    
    print(web_url,img_url,map_url)
    return web_url,img_url,map_url
    
#Attractions_recommend("樹太郎")