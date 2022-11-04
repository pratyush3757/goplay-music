import discord
import sqlite3
import logging
from typing import Optional
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger('discord.' + __name__)
logger.setLevel(logging.DEBUG)

show_id_numbers = True

class DbCommand():
    create_table_award_groups = """CREATE TABLE award_groups
        (group_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        image_link TEXT NOT NULL,
        PRIMARY KEY (group_id)
        )"""

    create_table_awards = """CREATE TABLE awards
        (award_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        group_id INTEGER NOT NULL,
        PRIMARY KEY (award_id),
        FOREIGN KEY (group_id) REFERENCES award_groups (group_id)
        ON DELETE CASCADE ON UPDATE NO ACTION
        )"""

    create_table_nominees = """CREATE TABLE nominees
        (nominee_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        link TEXT NOT NULL,
        image_link TEXT,
        award_id INTEGER NOT NULL,
        PRIMARY KEY (nominee_id),
        FOREIGN KEY (award_id) REFERENCES awards (award_id)
        ON DELETE CASCADE ON UPDATE NO ACTION
        )"""

    create_table_votes = """CREATE TABLE votes
        (vote_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        PRIMARY KEY (vote_id)
        )"""

    query_list_tables = "SELECT name FROM sqlite_master"

    query_full_tree = """SELECT
        g.group_id, g.name, g.description, g.image_link,
        a.award_id, a.name, a.description,
        n.nominee_id, n.name, n.description, n.link
        FROM award_groups g 
        LEFT JOIN awards a ON g.group_id = a.group_id
        LEFT JOIN nominees n ON a.award_id = n.award_id
        ORDER BY g.group_id, a.award_id, n.nominee_id"""

    query_all_award_groups = "SELECT group_id, name, description, image_link FROM award_groups ORDER BY group_id"
    
    #TODO: Change order of columns
    query_all_awards = """SELECT
        a.award_id, a.name, a.description, 
        g.group_id, g.name, g.description, g.image_link
        FROM award_groups g LEFT JOIN awards a
        ON g.group_id = a.group_id
        ORDER BY g.group_id, a.award_id"""

    #TODO: Change order of columns
    def query_all_award_nominees(award_id: int) -> str:
        return (f"SELECT n.nominee_id, n.name, n.description, n.link, n.image_link, "
                f"a.award_id, a.name, a.description "
                f"FROM nominees n LEFT JOIN awards a "
                f"ON n.award_id = a.award_id "
                f"WHERE n.award_id = {award_id} "
                f"ORDER BY n.nominee_id")
    
    #def query_award_group(group_id: int) -> str:
        #return f"SELECT group_id, name, description, image_link FROM award_groups WHERE group_id = {group_id}"

    def query_entry(entry_id: int, entry_type: str, table: str, columns: str) -> str:
        return f"SELECT {columns} FROM {table} WHERE {entry_type}_id = {entry_id}"

    #def query_award(award_id: int) -> str:
        #return f"SELECT award_id, name, description, group_id FROM awards WHERE award_id = {award_id}"

    #def query_nominee(nominee_id) -> str:
        #return f"SELECT nominee_id, name, description, link, image_link, award_id FROM nominees WHERE nominee_id = {nominee_id}"

    def add_entry(table: str, columns: str, add_value_string: str) -> str:
        return f"INSERT INTO {table} ({columns}) VALUES ({add_value_string})"

    #def add_award_group(group_id: int, name: str, image_link: str, description: str) -> str:
        #return (f"INSERT INTO award_groups (group_id, name, image_link, description) "
                #f"VALUES ({group_id}, '{name}', '{image_link}', '{description}')")

    #def add_award(award_id: int, name: str, description: str, group_id: int) -> str:
        #return (f"INSERT INTO awards (award_id, name, description, group_id) VALUES "
                #f"({award_id}, '{name}', '{description}', {group_id})")

    #def add_nominee(nominee_id: int, name: str, link: str, award_id: int, description: str, image_link: str) -> str:
        #return (f"INSERT INTO nominees (nominee_id, "
                #f"name, description, link, image_link, award_id) VALUES "
                #f"({nominee_id}, '{name}', '{description}', '{link}', '{image_link}', {award_id})")

    def update_entry(entry_id: int, entry_type: str, table: str, values) -> str:
        return f"UPDATE {table} SET {values} WHERE {entry_type}_id = {entry_id}"

    #def update_award_group(group_id: int, name: str, image_link: str, description: str) -> str:
        #values = ""
        #if name != "":
            #values += f"name = '{name}',"
        #if description != "":
            #values += f"description = '{description}',"
        #if image_link != "":
            #values += f"image_link = '{image_link}'"

        #return f"UPDATE award_groups SET {values} WHERE group_id = {group_id}"

    #def update_award(award_id: int, name: str, description: str, group_id: int) -> str:
        #values = ""
        #if name != "":
            #values += f"name = '{name}',"
        #if description != "":
            #values += f"description = '{description}',"
        #if group_id != 0:
            #values += f"group_id = {group_id}"
        #return f"UPDATE awards SET {values} WHERE award_id = {award_id}"

    #def update_nominee(nominee_id: int, name: str, link: str, award_id: int, description: str, image_link: str) -> str:
        #values = ""
        #if name != "":
            #values += f"name = '{name}',"
        #if description != "":
            #values += f"description = '{description}',"
        #if link != "":
            #values += f"link = '{link}',"
        #if image_link != "":
            #values += f"image_link = '{image_link}',"
        #if award_id != 0:
            #values += f"award_id = {award_id}"
        #return f"UPDATE nominees SET {values} WHERE nominee_id = {nominee_id}"

    #def remove_award_group(group_id: int) -> str:
        #return f"DELETE FROM award_groups WHERE group_id = {group_id}"
    
    def remove_entry(entry_id: int, entry_type: str, table: str) -> str:
        return f"DELETE FROM {table} WHERE {entry_type}_id = {entry_id}"    

class Dbconnection():
    def __init__(self) -> None:
        try:
            self.con = sqlite3.connect("db/gpca2023.db")
            # self.con.execute("PRAGMA foreign_keys = ON")
            logger.debug("Created connection to db")
            # self.missing = self.create_tables_if_missing()
            self.create_tables_if_missing()
        except sqlite3.Error as e:
            logger.error(str(e))
        except Exception as e:
            raise

    def __del__(self):
        self.con.close()
        logger.debug("Closed connection to db")

    @property
    def cursor(self):
        if self.connection:
            return self.connection.cursor()

    @property
    def connection(self):
        return self.con

    def create_tables_if_missing(self) -> None:
        try:
            tables = ["award_groups", "awards", "nominees", "votes"]
            cur = self.cursor
            res = cur.execute(DbCommand.query_list_tables)
            existing_tables = res.fetchall()
            existing_tables = [item[0] for item in existing_tables]
            #logger.debug(f"Existing tables: {existing_tables}")
            missing_tables = [item for item in tables if item not in existing_tables]
            #logger.debug(f"Tables missing: {missing_tables}")
            #missing_tables = list(set(tables).difference(res))
            for table in missing_tables:
                match table:
                    case "award_groups":
                        logger.debug(f"Creating table award_groups")
                        cur.execute(DbCommand.create_table_award_groups)
                    case "awards":
                        logger.debug(f"Creating table awards")
                        cur.execute(DbCommand.create_table_awards)
                    case "nominees":
                        logger.debug(f"Creating table nominees")
                        cur.execute(DbCommand.create_table_nominees)
                    case "votes":
                        logger.debug(f"Creating table votes")
                        cur.execute(DbCommand.create_table_votes)
                    case _:
                        pass
        except sqlite3.Error as e:
            logger.error(str(e))
            if self.connection:
                self.connection.rollback()
        except Exception as e:
            logger.error(str(e), exc_info = True)
            raise
        else:
            if self.connection:
                self.connection.commit()
            # return missing_tables

class SimpleMessage():
    def __init__(self, text: str = "", image: str = "", text_after_image: str = "") -> None:
        self.text = text
        self.image = image
        self.text_after_image = text_after_image

class TreeMessage():
    def __init__(self, group_text: str = "", image: str = "", award_texts_list: list[str] = []) -> None:
        self.group_text = group_text
        self.image = image
        self.award_texts_list = award_texts_list

class Entry():
    def __init__(self,
                 entry_type: str = "",
                 table: str = "",
                 columns_list: list[str] = [""]) -> None:
        self.entry_type = entry_type
        self.table = table
        self.columns_list = columns_list
        self.Db_connection = Dbconnection()
        self.parent = None

    @property
    def columns(self):
        return ', '.join(self.columns_list)
    
    def create_embed(self, entry: tuple) -> discord.Embed:
        return discord.Embed(title = None, description = None, color = discord.Color.gold())
    
    def query_entry(self, entry_id: int) -> tuple[bool, discord.Embed | None]:
        """Checks if entry exists, returns entry if true"""
        query = DbCommand.query_entry(entry_id, self.entry_type, self.table, self.columns)
        try:
            res = self.Db_connection.cursor.execute(query)
            data = res.fetchall()
            if len(data) == 0:
                return (False, None)
            
            entry = data[0]
            embed = self.create_embed(entry)
            return (True, embed)
        except Exception as e:
            logger.error(f"Entry query error: {e}")
            raise
    
    def check_then_add(self, entry_id: int, add_value_string: str) -> tuple[bool, discord.Embed | None]:
        add_query = DbCommand.add_entry(self.table, self.columns, add_value_string)
        try:
            entry_exists, embed = self.query_entry(entry_id)
            if entry_exists == True:
                return (False, embed)
            
            res = self.Db_connection.cursor.execute(add_query)
            self.Db_connection.connection.commit()
            return (True, None)
        except Exception as e:
            logger.error(f"Entry check_then_add error: {e}")
            raise
    
    def check_then_update(self, entry_id: int, update_value_string: str) -> tuple[bool, list[discord.Embed] | None]:
        update_query = DbCommand.update_entry(entry_id, self.entry_type, self.table, update_value_string)
        try:
            entry_exists, embed = self.query_entry(entry_id)
            if entry_exists == False:
                return (False, None)
            
            self.Db_connection.cursor.execute(update_query)
            self.Db_connection.connection.commit()
            entry_exists, updated_embed = self.query_entry(entry_id)

            return (True, [embed, updated_embed])
        except Exception as e:
            logger.error(f"Entry check_then_update error: {e}")
            raise

    def parent_entry_exists(self, parent_entry_id: int) -> bool:
        if self.parent is not None:
            return self.parent.query_entry(parent_entry_id)

    #def query_entry(self, entry_id: int) -> str:
        #return DbCommand.query_entry(entry_id, self.entry_type, self.table, self.columns)
    def remove_entry(self, entry_id: int) -> tuple[bool, discord.Embed | None]:
        remove_query = DbCommand.remove_entry(entry_id, self.entry_type, self.table)
        try:
            entry_exists, embed = self.query_entry(entry_id)
            if entry_exists == False:
                return (False, None)
            self.Db_connection.cursor.execute(remove_query)
            self.Db_connection.connection.commit()
            return (True, embed)
        except Exception as e:
            logger.error(f"Entry remove error: {e}")
            raise

    def query_full_tree(self) -> tuple[bool, list[TreeMessage] | None]:
        query = DbCommand.query_full_tree
        # g.group_id, g.name, g.description, g.image_link,
        # a.award_id, a.name, a.description,
        # n.nominee_id, n.name, n.description, n.link
        try:
            res = self.Db_connection.cursor.execute(query)
            data = res.fetchall()
            if len(data) == 0:
                return (False, None)
            
            tree = {}
            for entry in data:
                gid = entry[0]
                aid = entry[4]
                nid = entry[7]
                if gid not in tree.keys():
                    tree[gid] = {'name' : entry[1], 
                                'description' : entry[2], 
                                'image_link' : entry[3], 
                                'awards' : {}}
                if aid is not None:
                    logger.debug(tree[gid]['awards'].keys())
                    if aid not in tree[gid]['awards'].keys():
                        tree[gid]['awards'][aid] = {'name' : entry[5], 
                                                'description' : entry[6], 
                                                'nominees' : {}}
                    if nid is not None:
                        tree[gid]['awards'][aid]['nominees'][nid] = {'name' : entry[8], 
                                                                     'description' : entry[9], 
                                                                     'link' : entry[10]}
            message_list = []
            logger.debug(f"Award Tree: {tree}")
            for gk, gv in tree.items():
                gid = gk
                group_text = f"**{gv['name']}**"
                if gv['description'] != '':
                    group_text += f"\n**{gv['description']}**"
                if show_id_numbers == True:
                    group_text = f"**{gid}.** " + group_text
                
                image_link = gv['image_link']
                
                award_texts_list = []
                for ak, av in gv['awards'].items():
                    aid = ak
                    award_text = f"{av['name']}: {av['description']}"
                    if show_id_numbers == True:
                        award_text = f"{aid}. " + award_text
                    award_text = f"```{award_text}```\n"
                    
                    nominee_block = ""
                    for nk, nv in av['nominees'].items():
                        nid = nk
                        nominee_text = f"[{nv['name']}]({nv['link']})"
                        if nv['description'] != '':
                            nominee_text += f" - {nv['description']}"
                        nominee_text += "\n"
                        if show_id_numbers == True:
                            nominee_text = f"**{nid}. **" + nominee_text
                        nominee_block += nominee_text
                    if nominee_block != "":
                        award_text += f">>> {nominee_block}"
                    award_texts_list.append(award_text)
                
                message = TreeMessage(group_text = group_text, 
                                      image = image_link, 
                                      award_texts_list = award_texts_list)
                message_list.append(message)
            
            logger.debug(f"returning {message_list}")
            return (True, message_list)
        
        except Exception as e:
            logger.error(f"Error in Tree Query: {e}")

class AwardGroup(Entry):
    def __init__(self):
        super().__init__(entry_type = "group", table = "award_groups", columns_list = ["group_id", "name", "image_link", "description"])
    
    def create_embed(self, entry: tuple) -> discord.Embed:
        """Overriden method to match the class"""
        embed = discord.Embed(title = f"Group ID {entry[0]}. {entry[1]}",
                              description = entry[3] if (entry[3] != "") else None,
                              color =  discord.Color.gold()
                              )
        _image = entry[2] if (entry[2] != "") else None
        if _image is not None:
            embed.set_image(url = _image)

        return embed

    def list_all_entries(self) -> tuple[bool, list[SimpleMessage] | None]:
        query = DbCommand.query_all_award_groups
        # group_id, name, description, image_link
        try:
            res = self.Db_connection.cursor.execute(query)
            data = res.fetchall()
            if len(data) == 0:
                return (False, None)
            
            message_list = []
            for entry in data:
                text = f"{entry[0]}. {entry[1]}\n{entry[2]}"
                image = entry[3]
                message_list.append(SimpleMessage(text = text, image = image))
            return (True, message_list)
        except Exception as e:
            logger.error(e)
            raise
        
    def add_entry(self, group_id: int, name: str, image_link: str, description: str) -> tuple[bool, discord.Embed]:
        add_value_string = f"{group_id}, '{name}', '{image_link}', '{description}'"
        try:
            status, embed = self.check_then_add(group_id, add_value_string)
            if status == False:
                return (status, embed)
            
            return (True, self.create_embed((group_id, name, image_link, description)))
        except Exception as e:
            raise

    def update_entry(group_id: int, name: str, image_link: str, description: str) -> tuple[bool, list[discord.Embed] | None]:
        update_value_string = ""
        if name != "":
            update_value_string += f"name = '{name}',"
        if image_link != "":
            update_value_string += f"image_link = '{image_link}',"
        if description != "":
            update_value_string += f"description = '{description}'"
        
        try:
            status, embeds_list = self.check_then_update(group_id, update_value_string)
            if status == False:
                return (False, None)
            
            return (True, embeds_list)
        except Exception as e:
            raise

class Award(Entry):
    def __init__(self):
        super().__init__(entry_type = "award", table = "awards", columns_list = ["award_id", "name", "description", "group_id"])
        self.parent = AwardGroup()

    def create_embed(self, entry: tuple) -> discord.Embed:
        """Overriden method to match the class"""
        embed = discord.Embed(title = f"Award ID {entry[0]}. {entry[1]}",
                              description = entry[2] if (entry[2] != "") else None,
                              color =  discord.Color.gold()
                              ).set_footer(text = f"Group ID = {entry[3]}")
        return embed
    
    def list_all_entries(self) -> tuple[bool, list[SimpleMessage] | None]:
        query = DbCommand.query_all_awards
        # a.award_id, a.name, a.description, a.group_id, g.name, g.description, g.image_link
        try:
            res = self.Db_connection.cursor.execute(query)
            data = res.fetchall()
            if len(data) == 0:
                return (False, None)
            
            groups = {}
            for entry in data:
                if entry[3] not in groups.keys():
                    groups[entry[3]] = {'name' : entry[4],
                                        'description' : entry[5],
                                        'image' : entry[6],
                                        'awards' : [f"{entry[0]}. {entry[1]}: {entry[2]}"]}
                else:
                    groups[entry[3]]['awards'].append(f"{entry[0]}. {entry[1]}: {entry[2]}")
                    
            message_list = []
            for k, v in groups.items():
                text = f"{k}. {v['name']}\n{v['description']}"
                image = v['image']
                block_text = '\n'.join(v['awards'])
                text_after_image = f"```{block_text}```"
                message_list.append(SimpleMessage(text = text, image = image, text_after_image = text_after_image))
                
            return (True, message_list)
        except Exception as e:
            logger.error(e)
            raise

    def add_entry(self, award_id: int, name: str, description: str, group_id: int) -> tuple[bool, discord.Embed | None]:
        add_value_string = f"{award_id}, '{name}', '{description}', {group_id}'"
        try:
            # Parent entry is checked to enforce FK constraints, as sqlite3 doesn't by default
            parent_exists, _ = self.parent_entry_exists(group_id)
            if parent_exists == False:
                return (False, None)
            
            status, existing_entry_embed = self.check_then_add(award_id, add_value_string)
            if status == False:
                return (False, existing_entry_embed)
            
            return (True, self.create_embed((award_id, name, description, group_id)))
        except Exception as e:
            raise

    def update_entry(award_id: int, name: str, description: str, group_id: int) -> tuple[bool, list[discord.Embed] | None]:
        update_value_string = ""
        if name != "":
            update_value_string += f"name = '{name}',"
        if description != "":
            update_value_string += f"description = '{description}',"
        if group_id != 0:
            update_value_string += f"group_id = {group_id}"
            
        try:
            status, embeds_list = self.check_then_update(award_id, update_value_string)
            if status == False:
                return (False, None)
            
            return (True, embeds_list)
        except Exception as e:
            raise

class Nominee(Entry):
    def __init__(self):
        super().__init__(entry_type = "nominee", table = "nominees", columns_list = ["nominee_id", "name", "link", "award_id", "description", "image_link"])
        self.parent = Award()

    def create_embed(self, entry: tuple) -> discord.Embed:
        """Overriden method to match the class"""
        embed = discord.Embed(title = f"Nominee ID {entry[0]}. {entry[1]}",
                              description = entry[4] if (entry[4] != "") else None,
                              url = entry[2],
                              color =  discord.Color.gold()
                              ).set_footer(text = f"Award ID = {entry[3]}")
        _image = entry[5] if (entry[5] != "") else None
        if _image is not None:
            embed.set_image(url = _image)

        return embed

    def list_all_entries(self, parent_entry_id: int) -> tuple[bool, str | None]:
        query = DbCommand.query_all_award_nominees(parent_entry_id)
        # n.nominee_id, n.name, n.description, n.link, n.image_link, a.award_id, a.name, a.description
        try:
            res = self.Db_connection.cursor.execute(query)
            data = res.fetchall()
            if len(data) == 0:
                return (False, None)
            
            temp_entry = data[0]
            award_text = f"**Award {temp_entry[5]}: {temp_entry[6]}**\n\t_{temp_entry[7]}_"
            nominees = []
            for entry in data:
                text = f"{entry[0]}. [{entry[1]}]({entry[3]})"
                if entry[2] is not None:
                    text = text + f" - {entry[2]}"
                nominees.append(text)
            nominees = '\n'.join(nominees)
            message = award_text + "\n>>> " + nominees
            return (True, message)
        except Exception as e:
            logger.error(e)
            raise

    def add_entry(self, nominee_id: int, name: str, link: str, award_id: int, description: str, image_link: str) -> tuple[bool, discord.Embed | None]:
        add_value_string = f"{nominee_id}, '{name}', '{link}', {award_id}, '{description}', '{image_link}'"
        try:
            # Parent entry is checked to enforce FK constraints, as sqlite3 doesn't by default
            parent_exists, _ = self.parent_entry_exists(award_id)
            if parent_exists == False:
                return (False, None)
            
            status, existing_entry_embed = self.check_then_add(nominee_id, add_value_string)
            if status == False:
                return (False, existing_entry_embed)
            
            return (True, self.create_embed((nominee_id, name, link, award_id, description, image_link)))
        except Exception as e:
            raise

    def update_entry(nominee_id: int, name: str, link: str, award_id: int, description: str, image_link: str) -> tuple[bool, list[discord.Embed] | None]:
        update_value_string = ""
        if name != "":
            update_value_string += f"name = '{name}',"
        if link != "":
            update_value_string += f"link = '{link}',"
        if award_id != 0:
            update_value_string += f"award_id = {award_id},"
        if description != "":
            update_value_string += f"description = '{description}',"
        if image_link != "":
            update_value_string += f"image_link = '{image_link}'"
            
        try:
            status, embeds_list = self.check_then_update(nominee_id, update_value_string)
            if status == False:
                return (False, None)
            
            return (True, embeds_list)
        except Exception as e:
            raise

class Gpca(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    gpca_group = app_commands.Group(name = "gpca",
                                    description = "GPCA Commands")
    list_subgroup = app_commands.Group(name = "list",
                                       parent = gpca_group,
                                       description = "GPCA List Commands")
    add_subgroup = app_commands.Group(name = "add",
                                      parent = gpca_group,
                                      description = "GPCA Add Commands")
    update_subgroup = app_commands.Group(name = "update",
                                         parent = gpca_group,
                                         description = "GPCA Update Commands")
    remove_subgroup = app_commands.Group(name = "remove",
                                         parent = gpca_group,
                                         description = "GPCA Remove Commands")
    test_subgroup = app_commands.Group(name = "test",
                                       parent = gpca_group,
                                       description = "GPCA Test Commands")

    #def award_group_embed(self, entry: tuple) -> discord.Embed:
        #embed = discord.Embed(title = f"Group ID {entry[0]}. {entry[1]}",
                              #description = entry[2] if (entry[2] != "") else None,
                              #color =  discord.Color.gold()
                              #)
        #_image = entry[3] if (entry[3] != "") else None
        #if _image is not None:
            #embed.set_image(url = _image)

        #return embed

    #def award_embed(self, entry: tuple) -> discord.Embed:
        #embed = discord.Embed(title = f"Award ID {entry[0]}. {entry[1]}",
                              #description = entry[2] if (entry[2] != "") else None,
                              #color =  discord.Color.gold()
                              #)
        #return embed

    #def nominee_embed(self, entry: tuple) -> discord.Embed:
        #embed = discord.Embed(title = f"Nominee ID {entry[0]}. {entry[1]}",
                              #description = entry[2] if (entry[2] != "") else None,
                              #url = entry[3],
                              #color =  discord.Color.gold()
                              #)
        #_image = entry[4] if (entry[4] != "") else None
        #if _image is not None:
            #embed.set_image(url = _image)

        #return embed

    @app_commands.command(name = 'slashping')
    async def _slashping(self, interaction: discord.Interaction) -> None:
        """Ping pong using slash commands"""
        # /slashping

        await interaction.response.send_message('pong')

    @list_subgroup.command(name = "award_groups")
    @app_commands.describe(group_id = "Group number")
    async def _list_award_groups(self, interaction: discord.Interaction,
                                 group_id: Optional[int] = 0) -> None:
        """List all award groups or show a given group"""
        # /gpca list award_groups [arg]

        try:
            group = AwardGroup()
            if group_id != 0:
                status, embed = group.query_entry(group_id)
                if status == True:
                    return await interaction.response.send_message(embed = embed)
                else:
                    return await interaction.response.send_message(f"[Error] There's no group with the given id.")
            else:
                # TODO: Implement showing same-level entries
                status, message_list = group.list_all_entries()
                if status == True:
                    channel = interaction.guild.get_channel(interaction.channel_id)
                    await interaction.response.defer(ephemeral = False, thinking = True)
                    #await channel.send(f"GPCA 2023")
                    for message in message_list:
                        await channel.send(f"{message.text}")
                        if message.image != "":
                            await channel.send(f"{message.image}")
                    await interaction.followup.send("GPCA 2023 Award Groups", ephemeral = False)
                else:
                    return await interaction.response.send_message(f"[Error] No entries found.")
        except Exception as e:
            logger.error(e)
            await interaction.followup.send("[Error] The bot encountered an error", ephemeral = False)
            raise

    @list_subgroup.command(name = "awards")
    @app_commands.describe(award_id = "Award id number")
    async def _list_awards(self, interaction: discord.Interaction,
                           award_id: Optional[int] = 0) -> None:
        """List all awards, or show a given award"""
        # /gpca list awards [arg]
        
        try:
            award = Award()
            if award_id != 0:
                status, embed = award.query_entry(award_id)
                if status == True:
                    return await interaction.response.send_message(embed = embed)
                else:
                    return await interaction.response.send_message(f"[Error] There's no award with the given id.")
            else:
                # TODO: Implement showing same-level entries
                status, message_list = award.list_all_entries()
                if status == True:
                    channel = interaction.guild.get_channel(interaction.channel_id)
                    await interaction.response.defer(ephemeral = False, thinking = True)
                    #await channel.send(f"GPCA 2023")
                    for message in message_list:
                        logger.debug(f"[gpca list award] Sending award group text: {message.text}")
                        await channel.send(message.text)
                        if message.image != "":
                            logger.debug(f"[gpca list award] Sending award group image: {message.image}")
                            await channel.send(message.image)
                        if message.text_after_image != "":
                            logger.debug(f"[gpca list award] Sending award text: {message.text_after_image}")
                            await channel.send(message.text_after_image)
                    await interaction.followup.send("GPCA 2023 Awards", ephemeral = False)
                else:
                    return await interaction.response.send_message(f"[Error] No entries found.")
        except Exception as e:
            logger.error(e)
            await interaction.followup.send("[Error] The bot encountered an error", ephemeral = False)
            raise

    @list_subgroup.command(name = "nominees")
    @app_commands.describe(award_id = "Award id number",
                           nominee_id = "Nominee id number")
    async def _list_nominees(self, interaction: discord.Interaction,
                             nominee_id: Optional[int] = 0,
                             award_id: Optional[int] = 0) -> None:
        """List all nominees for an award, or show a given nominee. Nominee id is given preference over Award id."""
        # /gpca list nominees [arg]

        try:
            nominee = Nominee()
            if nominee_id != 0:
                status, embed = nominee.query_entry(nominee_id)
                if status == True:
                    return await interaction.response.send_message(embed = embed)
                else:
                    return await interaction.response.send_message(f"No entry found with nominee id = {nominee_id}")
            elif award_id != 0:
                status, message = nominee.list_all_entries(award_id)
                if status == True:
                    logger.debug(f"[gpca list nominees] Sending nominee text: {message}")
                    return await interaction.response.send_message(message)
                else:
                    return await interaction.response.send_message(f"No entry found with award id = {award_id}")
            else:
                return await interaction.response.send_message(f"Please check any one option.")
        except Exception as e:
            logger.error(e)
            await interaction.followup.send("[Error] The bot encountered an error", ephemeral = False)
            raise

    @list_subgroup.command(name = "all")
    async def _list_all(self, interaction: discord.Interaction) -> None:
        """Show the complete gpca tree"""
        # /gpca list all

        try:
            group = AwardGroup()
            status, message_list = group.query_full_tree()
            if status == True:
                # return await interaction.response.send_message("[prevent rate limit during testing] Check logs for the output", ephemeral = False)
                channel = interaction.guild.get_channel(interaction.channel_id)
                await interaction.response.defer(ephemeral = False, thinking = True)
                #await channel.send(f"GPCA 2023")
                for message in message_list:
                    logger.debug(f"[gpca tree] Sending award group text: {message.group_text}")
                    await channel.send(f"{message.group_text}")
                    if message.image != "":
                        logger.debug(f"[gpca tree] Sending award group image: {message.image}")
                        await channel.send(f"{message.image}")
                    for award_message in message.award_texts_list:
                        logger.debug(f"[gpca tree] Sending award/nominee text: {award_message}")
                        msg_handle = await channel.send(f"{award_message}")
                        await msg_handle.edit(suppress=True)
                await interaction.followup.send("GPCA 2023", ephemeral = False)
            else:
                logger.error("_list_all: There is no entry to show")
                await interaction.response.send_message("[Error] There is no entry to show", ephemeral = False)
        except Exception as e:
            logger.error(e)
            await interaction.followup.send("Error in showing data.", ephemeral = False)
            raise
        #await interaction.response.send_message(f"showing gpca tree")

    @add_subgroup.command(name = "award_group")
    @app_commands.describe(group_id = "Group number",
                           name = "Name of entry",
                           image_link = "Link to the banner",
                           description = "About the group")
    async def _add_award_group(self, interaction: discord.Interaction,
                               group_id: int,
                               name: str,
                               image_link: str,
                               description: Optional[str] = "") -> None:
        """Add a new award group"""
        # /gpca add award_group args

        try:
            group = AwardGroup()
            status, embed = group.add_entry(group_id = group_id,
                                            name = name,
                                            image_link = image_link,
                                            description = description)
            if status == True:
                return await interaction.response.send_message(f"The entry has been added.", embed = embed)
            else:
                return await interaction.response.send_message(f"[Error] There's already an entry for the group_id {group_id}:", embed = embed)
        except Exception as e:
            logger.error(e)
            raise

    @add_subgroup.command(name = "award")
    @app_commands.describe(award_id = "Id number of the award",
                           name = "Name of entry",
                           description = "About the award",
                           group_id = "Group number to put the award into")
    async def _add_award(self, interaction: discord.Interaction,
                         award_id: int,
                         name: str,
                         description: str,
                         group_id: int) -> None:
        """Add a new award"""
        # /gpca add award args

        try:
            award = Award()
            status, embed = award.add_entry(award_id = award_id,
                                            name = name,
                                            description = description,
                                            group_id = group_id)
            if status == True:
                return await interaction.response.send_message(f"The entry has been added.", embed = embed)
            else:
                if embed is None:
                    return await interaction.response.send_message(f"[Error] There's no parent group with id {group_id}.")
                else:
                    return await interaction.response.send_message(f"[Error] There's already an entry for the award_id {award_id}:", embed = embed)
        except Exception as e:
            logger.error(e)
            raise

    @add_subgroup.command(name = "nominee")
    @app_commands.describe(nominee_id = "Id number of the nominee",
                           name = "Name of entry",
                           link = "Link to page about the nominee",
                           award_id = "Award number to put the nominee into",
                           description = "Additional info",
                           image_link = "Link to banner image")
    async def _add_nominee(self, interaction: discord.Interaction,
                           nominee_id: int,
                           name: str,
                           link: str,
                           award_id: int,
                           description: Optional[str] = "",
                           image_link: Optional[str] = "") -> None:
        """Add a new nominee"""
        # /gpca add nominee args
        
        try:
            nominee = Nominee()
            status, embed = nominee.add_entry(nominee_id = nominee_id,
                                              name = name,
                                              link = link,
                                              award_id = award_id,
                                              description = description,
                                              image_link = image_link)
            if status == True:
                return await interaction.response.send_message(f"The entry has been added.", embed = embed)
            else:
                if embed is None:
                    return await interaction.response.send_message(f"[Error] There's no parent award with id {award_id}.")
                else:
                    return await interaction.response.send_message(f"[Error] There's already an entry for the nominee_id {nominee_id}:", embed = embed)
        except Exception as e:
            logger.error(e)
            raise


    @update_subgroup.command(name = "award_group")
    @app_commands.describe(group_id = "Group number",
                           name = "Name of entry",
                           image_link = "Link to the banner",
                           description = "About the group")
    async def _update_award_group(self, interaction: discord.Interaction,
                                  group_id: int,
                                  name: Optional[str] = "",
                                  image_link: Optional[str] = "",
                                  description: Optional[str] = "") -> None:
        """Update an existing award group"""
        # /gpca update award_group args

        try:
            if name == "" and image_link == "" and description == "":
                return await interaction.response.send_message(f"Please give atleast one field to update.")

            group = AwardGroup()
            status, embeds_list = group.update_entry(group_id = group_id,
                                                     name = name,
                                                     image_link = image_link,
                                                     description = description)
            if status == True:
                return await interaction.response.send_message(f"The entry has been updated. Before and after update:", embeds = embeds_list)
            else:
                return await interaction.response.send_message(f"[Error] There's no entry for the group_id {group_id}")
        except Exception as e:
            logger.error(e)
            raise

    @update_subgroup.command(name = "award")
    @app_commands.describe(award_id = "Id number of the award",
                           name = "Name of entry",
                           description = "About the award",
                           group_id = "Group number to put the award into")
    async def _update_award(self, interaction: discord.Interaction,
                            award_id: int,
                            name: Optional[str] = "",
                            description: Optional[str] = "",
                            group_id: Optional[int] = 0) -> None:
        """Update an existing award"""
        # /gpca update award args

        try:
            if name == "" and description == "" and group_id == 0:
                return await interaction.response.send_message(f"Please give atleast one field to update.")

            award = Award()
            status, embeds_list = award.update_entry(award_id = award_id,
                                                     name = name,
                                                     description = description,
                                                     group_id = group_id)
            if status == True:
                return await interaction.response.send_message(f"The entry has been updated. Before and after update:", embeds = embeds_list)
            else:
                return await interaction.response.send_message(f"[Error] There's no entry for the award_id {award_id}")
        except Exception as e:
            logger.error(e)
            raise

    @update_subgroup.command(name = "nominee")
    @app_commands.describe(nominee_id = "Id number of the nominee",
                           name = "Name of entry",
                           link = "Link to page about the nominee",
                           award_id = "Award number to put the nominee into",
                           description = "Additional info",
                           image_link = "Link to banner image")
    async def _update_nominee(self, interaction: discord.Interaction,
                              nominee_id: int,
                              name: Optional[str] = "",
                              link: Optional[str] = "",
                              award_id: Optional[int] = 0,
                              description: Optional[str] = "",
                              image_link: Optional[str] = "") -> None:
        """Update an existing nominee"""
        # /gpca update nominee args

        try:
            if name == "" and link == "" and award_id == 0 and description == "" and image_link == "":
                return await interaction.response.send_message(f"Please give atleast one field to update.")

            nominee = Nominee()
            status, embeds_list = nominee.update_entry(nominee_id = nominee_id,
                                                       name = name,
                                                       link = link,
                                                       award_id = award_id,
                                                       description = description,
                                                       image_link = image_link)
            if status == True:
                return await interaction.response.send_message(f"The entry has been updated. Before and after update:", embeds = embeds_list)
            else:
                return await interaction.response.send_message(f"[Error] There's no entry for the nominee_id {nominee_id}")
        except Exception as e:
            logger.error(e)
            raise

    @remove_subgroup.command(name = "award_group")
    @app_commands.describe(group_id = "Group number")
    async def _remove_award_group(self, interaction: discord.Interaction, group_id: int) -> None:
        """Remove an existing award group. CAUTION: Will delete all its sub-entries."""
        # /gpca remove award_group args

        try:
            group = AwardGroup()
            status, embed = group.remove_entry(group_id)
            if status == True:
                return await interaction.response.send_message(f"The following entry (and all its sub-entries) has been removed:", embed = embed)
            else:
                return await interaction.response.send_message(f"[Error] There's no entry for the group_id {group_id}")
        except Exception as e:
            logger.error(e)
            raise

    @remove_subgroup.command(name = "award")
    @app_commands.describe(award_id = "Award number")
    async def _remove_award(self, interaction: discord.Interaction, award_id: int) -> None:
        """Remove an existing award. CAUTION: Will delete all its sub-entries."""
        # /gpca remove award args

        try:
            award = Award()
            status, embed = award.remove_entry(award_id)
            if status == True:
                return await interaction.response.send_message(f"The following entry (and all its sub-entries) has been removed:", embed = embed)
            else:
                return await interaction.response.send_message(f"[Error] There's no entry for the award {award_id}")
        except Exception as e:
            logger.error(e)
            raise

    @remove_subgroup.command(name = "nominee")
    @app_commands.describe(nominee_id = "Nominee number")
    async def _remove_nominee(self, interaction: discord.Interaction, nominee_id: int) -> None:
        """Remove an existing nominee. CAUTION: Will delete all its sub-entries."""
        # /gpca remove nominee args

        try:
            nominee = Nominee()
            status, embed = nominee.remove_entry(nominee_id)
            if status == True:
                return await interaction.response.send_message(f"The following entry (and all its sub-entries) has been removed:", embed = embed)
            else:
                return await interaction.response.send_message(f"[Error] There's no entry for the nominee {nominee_id}")
        except Exception as e:
            logger.error(e)
            raise

    @commands.command(name = 'sync', hidden = True)
    @commands.is_owner()
    async def _sync(self, ctx: commands.Context):
        """Sync all slash commands with discord"""

        fmt = await ctx.bot.tree.sync()
        await ctx.send(f"Synced {len(fmt)} commands to the current guild.")

    @commands.command(name = 'tables', hidden = True)
    @commands.is_owner()
    async def _tables(self, ctx: commands.Context):
        """Create tables"""

        try:
            a = Dbconnection()
            missing_tables = a.missing
        except Exception as e:
            pass
        else:
            await ctx.send(f"Created {missing_tables} tables.")

async def setup(bot):
    await bot.add_cog(Gpca(bot))

if __name__ == '__main__':
    #db = Dbconnection()
    #res = db.cursor.execute(DbCommand.query_all_award_groups)
    entry = AwardGroup()
    print(entry.query_entry(1))
    entry = Award()
    print(entry.query_entry(1))
    entry = Nominee()
    print(entry.query_entry(1))
