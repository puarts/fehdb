#!/usr/bin/env python
# coding: utf-8

import datetime
import os

def getTodayYear():
    today = datetime.date.today()
    formatted_date = today.strftime('%Y')
    return formatted_date

class FeCharInfo:
    def __init__(self, name, series, english_name, thumb, birthday, birthYear):
        self.name = name
        self.series = [word for word in series.split("|") if word]
        self.english_name = english_name
        self.thumb = thumb
        self.birthday = birthday
        self.birthYear = f"{birthYear}"

    def toArray(self):
        seriesText = str.join(u"|", self.series)
        if seriesText != "":
            seriesText = f"|{seriesText}|"
        return [self.name, seriesText, self.english_name, self.thumb, self.birthday, self.birthYear]

    def toTsv(self):
        return str.join("\t", self.toArray())

    def toDisplayName(self):
        seriesText = str.join(u"、", self.series)
        if seriesText != "":
            seriesText = "(%s)"%seriesText
        birthYear = self.birthYear
        if birthYear != "":
            currentYear = getTodayYear()
            diffYear = int(currentYear) - int(birthYear)
            birthYear = f"({diffYear}周年)"
        return "%s%s%s"%(self.name, seriesText, birthYear)
    
    def getOriginEnglishName(self):
        if len(self.series) == 0: return ""
     
        origin = self.series[0]
        if origin == "覚醒": return "Awakening"
        if origin == "if": return "Fates"
        if origin == "風花雪月": return "Three Houses"
        if origin == "エンゲージ": return "Engage"
        if origin == "幻影異聞録♯FE Encore": return "Tokyo Mirage Sessions #FE Encore"
        return ""

    def getOriginalCharacterImagePathFromEnglishName(self, charThumbRoot, titleThumbRoot):
        root = charThumbRoot
        if self.thumb != "" and self.thumb is not None:
            filePathNormal = root + self.thumb
            if os.path.exists(filePathNormal):
                return filePathNormal
            filePathNormal = titleThumbRoot + self.thumb
            if os.path.exists(filePathNormal):
                return filePathNormal
            return ""
        englishName = self.english_name
        englishName = englishName.replace("'", "")
        englishName = englishName.replace("& ", "")
        englishName = englishName.replace("ó", "o")
        englishName = englishName.replace("Ó", "O")
        englishName = englishName.replace("ö", "o")
        englishName = englishName.replace("á", "a")
        englishName = englishName.replace("ú", "u")
        englishName = englishName.replace("í", "i")
        englishName = englishName.replace("é", "e")
        englishName = englishName.replace(" ", "_")
        englishName = englishName.replace("ð", "o")

        # name = rowData["name"]
        # if (
        #     mb_strpos(name, "女") === (mb_strlen(name) - 1)
        #     || name === "ベレス"
        # ) {
        #     englishName .= "_female"
        # } else if (
        #     mb_strpos(name, "男") === (mb_strlen(name) - 1)
        #     || name === "ベレト"
        # ) {
        #     englishName .= "_male"
        # }

        # series = rowData["series"]
        # seriesName = ""
        # foreach (parseSqlStringToArray(series) as seriesUnit) {
        #     queryResult = this->db->queryWrap("SELECT * FROM series where title like 'seriesUnit%'")
        #     seriesRowData = queryResult->fetchArray(SQLITE3_ASSOC)
        #     if (seriesRowData == null) {
        #         return ""
        #     }
        #     seriesName .=  seriesRowData["english_title"] . " "
        # }

        seriesName = self.getOriginEnglishName()
        seriesName = seriesName.replace(" ", "_")
        seriesName = seriesName.replace(":", "" )
        seriesName = seriesName.replace("#", "" )

        # if (seriesName === "Shadow_Dragon") {
        #     seriesName = "Shadow_Dragon_and_the_Blade_of_Light_Shadow_Dragon"
        # } else if (seriesName === "New_Mystery_of_the_Emblem") {
        #     seriesName = "Mystery_of_the_Emblem_New_Mystery_of_the_Emblem"
        # }

        basePathToName = root + "CYL_" + englishName
        basePath = basePathToName + "_" + seriesName
        filePathNormal = basePath + ".png"
        # variation = rowData["variation"]
        if "風花雪月" in self.series:
            # if (variation === "変化後") {
            #     basePath = basePathToName . "_Enlightened_seriesName"
            # }
            suffixList = [
                "_War_Arc",
                "_Academy_Arc"
            ]
            for suffix in suffixList:
                filePath = basePath + suffix + ".png"
                if os.path.exists(filePath):
                    return filePath
                
        # else if (mb_strpos(series, "聖戦の系譜") !== false) {
        #     if (variation === "物語前半") {
        #         filePath = "basePath" . "_G1.png"
        #         if (file_exists("./" . filePath)) {
        #             return filePath
        #         }
        #     } else if (variation === "物語後半") {
        #         filePath = "basePath" . "_G2.png"
        #         if (file_exists("./" . filePath)) {
        #             return filePath
        #         }
        #     }
        # }

        if os.path.exists(filePathNormal):
            return filePathNormal
        return ""