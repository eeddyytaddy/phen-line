import pandas as pd
from random import randrange
def Attractions_recommend(recommend):
    Attractions = pd.read_csv('penghu_id.csv',encoding='utf-8-sig')
    Attractions_id = Attractions["id"]
    Attractions_html = Attractions["html"]
    Attractions_imgur = Attractions["imgur"]
    Attractions_map = Attractions["map"]
    for i in range(0,217):
        if Attractions_id[i] == recommend :
            recommend_website = Attractions_html[i]
            recommend_imgur = Attractions_imgur[i]
            recommend_map = Attractions_map[i]
            #print(recommend_website,recommend_imgur,recommend_map)
            break
        # else:
        #     i = randrange(0,6)
        #     recommend_website = Attractions_html[i]
        #     recommend_imgur = Attractions_imgur[i]
        #     recommend_map = Attractions_map[i]
    return recommend_website,recommend_imgur,recommend_map

    
def Attractions_recommend1(recommend):
    Attractions1 = pd.read_csv('penghu_id_sustainable.csv',encoding='utf-8-sig')
    Attractions_id1 = Attractions1["id"]
    Attractions_html1 = Attractions1["html"]
    Attractions_imgur1 = Attractions1["imgur"]
    Attractions_map1 = Attractions1["map"]
    for i in range(0,217):
        if Attractions_id1[i] == recommend :
            recommend_website1 = Attractions_html1[i]
            recommend_imgur1 = Attractions_imgur1[i]
            recommend_map1 = Attractions_map1[i]
            #print(recommend_website,recommend_imgur,recommend_map)
            break           
    return recommend_website1,recommend_imgur1,recommend_map1
        
      