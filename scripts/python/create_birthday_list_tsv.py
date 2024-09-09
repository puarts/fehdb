#!/usr/bin/env python
# coding: utf-8

import datetime
import csv
import charinfo
import os

g_siteRoot = os.path.join(os.path.dirname(__file__), "../../..")
g_thumbRoot = os.path.join(g_siteRoot , "images/FehCylPortraits/")
g_titleThumbRoot = os.path.join( g_siteRoot, "images/FeTitleImages/")
g_dbPath = os.path.join(g_siteRoot, "db/feh-original_heroes.sqlite3")
g_titleDbPath = os.path.join(g_siteRoot, "db/feh.sqlite3")


def write_fecharinfo_to_tsv(fecharinfo_list, tsv_file_path):
    with open(tsv_file_path, 'w', newline='', encoding="utf-8") as f:
        writer = csv.writer(f, delimiter='\t')
        for info in fecharinfo_list:
            writer.writerow(info.toArray())

def getBirthdayFeTitleInfosBySqlite3All():
    return getBirthdayFeTitleInfosBySqlite3WithCondition('')


def getBirthdayFeTitleInfosBySqlite3WithCondition(condition):
    import sqlite3
    connection = sqlite3.connect(g_titleDbPath)

    cursor = connection.cursor()

    # データを取得
    cursor.execute(f'SELECT title,english_title,release_date,id FROM series {condition}')
    infos = []
    for row in cursor.fetchall():
        name = row[0]
        series = ""
        english_name = row[1]
        thumb = f"Package-{row[3]}.png"
        dt = datetime.datetime.strptime(row[2], "%Y-%m-%d")
        birthday = "%s/%s"%(str(dt.month).zfill(2), str(dt.day).zfill(2))
        birthYear = dt.year
        info = charinfo.FeCharInfo(name, series, english_name, thumb, birthday, birthYear)
        if info.getOriginalCharacterImagePathFromEnglishName(g_thumbRoot, g_titleThumbRoot) == "":
            info.thumb = f"Package-{row[3]}.jpg"
        infos.append(info)

    connection.close()
    return infos

def getBirthdayFeCharInfosBySqlite3(currentDate):
    import sqlite3
    connection = sqlite3.connect(g_dbPath)

    cursor = connection.cursor()

    # データを取得
    cursor.execute('SELECT name,series,english_name,thumb,birthday FROM original_heroes where birthday="%s"'%currentDate)
    infos = []
    for row in cursor.fetchall():
        name = row[0]
        series = row[1]
        english_name = row[2]
        thumb = [3]
        birthday = [4]
        infos.append(charinfo.FeCharInfo(name, series, english_name, thumb, birthday, ""))

    connection.close()
    return infos

def getBirthdayFeCharInfosBySqlite3All():
    import sqlite3
    connection = sqlite3.connect(g_dbPath)

    cursor = connection.cursor()

    # データを取得
    cursor.execute('SELECT name,series,english_name,thumb,birthday FROM original_heroes where birthday is not null and birthday!=""')
    infos = []
    for row in cursor.fetchall():
        name = row[0]
        series = row[1]
        english_name = row[2]
        thumb = [3]
        birthday = [4]
        infos.append(charinfo.FeCharInfo(name, series, english_name, thumb, birthday, ""))

    connection.close()
    return infos

def sqlite3ToTsv():
    charTsvPath = os.path.join(g_siteRoot, "db/fe-char-birthdays.tsv")
    titleTsvPath = os.path.join(g_siteRoot, "db/fe-title-birthdays.tsv")

    # FE キャラ
    infos = getBirthdayFeCharInfosBySqlite3All()
    write_fecharinfo_to_tsv(infos, charTsvPath)
    print(f"save to {charTsvPath}")
    
    # FE タイトル
    infos = getBirthdayFeTitleInfosBySqlite3All()
    write_fecharinfo_to_tsv(infos, titleTsvPath)
    print(f"save to {titleTsvPath}")

sqlite3ToTsv()
