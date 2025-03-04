from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser, PydanticOutputParser
from DatabaseManager import DatabaseManager
from LLMManager import LLMManager
import json
from pydantic import BaseModel, Field
import pandas as pd

## NEW: Enforce JSON structure using Pydantic
class ParsedQuestionResponse(BaseModel):
    """Defines the expected LLM response structure for parse_question."""
    is_relevant: bool = Field(default=False, description="Indicates if the question is relevant.")
    relevant_tables: list = Field(default=[], description="Relevant tables and columns.")

class SQLQueryResponse(BaseModel):
    """Defines the structure of the expected LLM response."""
    query: str = Field(..., description="SQL query to fetch sales data.")

class SQLAgent:
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.llm_manager = LLMManager()
        self.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)  # ✅ Add Memory
    
    def remember(self, user_input, agent_response):
        """Store user input and agent's response in memory."""
        self.memory.save_context({"input": user_input}, {"output": agent_response})

    def get_memory(self):
        """Retrieve conversation history."""
        return self.memory.load_memory_variables({})

    def parse_question(self, state: dict) -> dict:
        """Parse user question and identify relevant tables and columns and store in memory."""
        question = state['question']

        # ✅ Fetch chat memory
        chat_history = self.memory.load_memory_variables({})["chat_history"]
        self.memory.save_context({"input": question}, {"output": "Processing..."})  # ✅ Store User Input

        schema = self.db_manager.get_schema()

        prompt = ChatPromptTemplate.from_messages([
            ("system", '''You are a data analyst that can help summarize SQL tables and parse user questions about a database. 
Given the question and database schema, identify the relevant tables and columns. 
If the question is not relevant to the database or if there is not enough information to answer the question, set is_relevant to false.
    
    **IMPORTANT:** Respond strictly in valid **JSON format only**.
    **Instructions**
1. Identify only the most relevant tables and columns needed to answer the user's question.  
2. Prioritize key columns over less useful ones. For example:
   - 'modelo_tipo' is important when filtering motorcycles.
   - 'grupo_modelo_veiculo' is less useful and should only be included if 'modelo_tipo' is missing.
   - 'ano_emplacamento' is always relevant for date-based queries.  
3. DO NOT include columns that are redundant or less specific. 
4. Return the response in JSON format** with the most relevant columns only.
5. column razao_social is not very important, unless explicit  on the question.

    Your response should be in the following JSON format:
{{
    "is_relevant": boolean,
    "relevant_tables": [
        {{
            "table_name": string,
            "columns": [string],
            "noun_columns": [string]
        }}
    ]
}}

The "noun_columns" field should contain only the columns that are relevant to the question and contain nouns or names, for example, the column "Artist name" contains nouns relevant to the question "What are the top selling artists?", but the column "Artist ID" is not relevant because it does not contain a noun. Do not include columns that contain numbers.'''),
            ("human", "===Database schema:\n{schema}\n\n===User question:\n{question}\n\nIdentify relevant tables and columns:")
        ])
        output_parser = JsonOutputParser()

        try:
            # ✅ Parse question with chat memory
            response = self.llm_manager.invoke(prompt, schema=schema, question=question, chat_history=chat_history)
            parsed_response = JsonOutputParser().parse(response)

            self.memory.save_context({"input": question}, {"output": f"Parsed Response: {parsed_response}"})  # ✅ Store in Memory
            return {"parsed_question": parsed_response}
    
        except Exception as e:
            error_message = f"❌ ERROR parsing question: {e}"
            self.memory.save_context({"input": question}, {"output": error_message})  # ✅ Store error in Memory
            print(error_message)
            return {"parsed_question": {"is_relevant": False, "relevant_tables": []}}
        except json.JSONDecodeError:
            error_message = "❌ JSONDecodeError: LLM response is not valid JSON."
            self.remember(question, error_message)  # ✅ Store Error in Memory
            print(error_message, response)
            return {"parsed_question": {"query": "ERROR"}}  # Return fallback

        except KeyError as e:
            error_message = f"❌ KeyError: Missing key in LLM response: {e}"
            self.remember(question, error_message)  # ✅ Store Error in Memory
            print(error_message)
            return {"parsed_question": {"query": "ERROR"}}

        except ValueError as e:
            error_message = f"❌ ValueError: {e}"
            self.remember(question, error_message)  # ✅ Store Error in Memory
            print(error_message)
            return {"parsed_question": {"query": "ERROR"}}

    def get_unique_nouns(self, state: dict) -> dict:
        """Find unique nouns in relevant tables and columns."""
        parsed_question = state['parsed_question']
        
        # ✅ FIX: Default to False if "is_relevant" is missing
        is_relevant = parsed_question.get("is_relevant", False)
        # 🔥 DEBUG: Confirm "is_relevant" before processing
        print(f"\n🔍 DEBUG: is_relevant in get_unique_nouns: {is_relevant}")

        # if not is_relevant:
        if not parsed_question['is_relevant']:
            return {"unique_nouns": []}

        unique_nouns = set()
        for table_info in parsed_question['relevant_tables']:
            table_name = table_info['table_name']
            noun_columns = table_info['noun_columns']
            
            if noun_columns:
                # ✅ FIX: Use SQL Server-compatible syntax with square brackets
                column_names = ', '.join(f"[{col}]" for col in noun_columns)
                table_name = f"[{table_name}]"  # Convert table name to square brackets
                query = f"SELECT DISTINCT {column_names} FROM {table_name}"
                results = self.db_manager.execute_query(query)
                for row in results:
                    unique_nouns.update(str(value) for value in row if value)
                print("TESTE", unique_nouns)
                try:
                        print(f"\n🔍 DEBUG: Running query -> {query}")
                        results = self.db_manager.execute_query(query)
                        for row in results:
                            unique_nouns.update(str(value) for value in row if value)
                except Exception as e:
                    print(f"❌ ERROR: Exception in get_unique_nouns - {e}")
                    return {"unique_nouns": []}

        return {"unique_nouns": list(unique_nouns)}
        # state["unique_nouns"] = list(unique_nouns)  # ✅ Store in state
        # return state

    def generate_sql(self, state: dict) -> dict:
        """Generate SQL query based on parsed question and unique nouns."""
        question = state['question']
        parsed_question = state['parsed_question']
        unique_nouns = state['unique_nouns']

        # ✅ Fetch chat memory
        chat_history = self.memory.load_memory_variables({})["chat_history"]

        # ✅ Check if question is relevant
        if not parsed_question['is_relevant']:
            self.memory.save_context({"input": question}, {"output": "❌ No relevant tables found. Query marked as NOT_RELEVANT."})
            return {"sql_query": "NOT_RELEVANT", "is_relevant": False}
    
        # schema = self.db_manager.get_schema(state['uuid'])
        schema = self.db_manager.get_schema()

        prompt = ChatPromptTemplate.from_messages([
            ("system", r''' You are an AI assistant that generates SQL queries based on user questions, database schema, and unique nouns found in the relevant tables. Generate a valid SQL query to answer the user's question.
             Retun MAX the first 10 answer.
             ALWAYS when the question has the city/municipy São Paulo, change to Sao Paulo.
             If there is not enough information to write a SQL query, respond with "NOT_ENOUGH_INFO".
             Here are some examples for generates SQL queries for an Azure SQL Database.
             Follow these rules strictly:
             Table and column names should NOT use backticks (`). Use regular SQL syntax.  
             Always include the correct schema for tables, e.g., '[tbl_emplacamento]', [br_gov_motorcycle_metrics_sample].  
             Limit the result to the first 10 rows, ALWAYS.
             Use TOP for SQL instead of LIMIT.
             For text searches, always use LIKE '%term%' instead of =.
             If the question asks for all the records, bring everything and not just the top 10.
             Ensure correct spelling of nouns as provided in the unique nouns list.
             Se na tabela não houver informação suficiente para gerar a query, se sinta livre para completar a informação, utilizando seus conhecimentos gerais.
             Quando a pergunta for IMPORTADO/S, IMPORTADA/S, OU NACIONAL, utilizar no filtro quando a coluna MODELO começar com I/, isso significa que o modelo é IMPORTADO/IMPORTADA.
             SEMPRE que a pergunta for sobre CATEGORIA, busque dados do campo "segmento".
             SEMPRE que a pergunta for sobre "ranking", ordernar pela coluna com os valores do ranking.

             Correct Format:
             ```sql
             SELECT DISTINCT modelo FROM [tbl_emplacamento] ORDER BY modelo;
             ```

             Here are some examples:

             1. Quais são os modelos distintos de veículos armazenados no banco de dados? Retorne apenas os nomes dos modelos de forma única, ordenados alfabeticamente.? 
             Answer: SELECT DISTINCT modelo FROM [tbl_emplacamento] ORDER BY modelo;
             
             2. Quais são os municípios com o maior número de motos emplacadas no ano de 2014? Retorne a contagem total de motos por município, ordenada do maior para o menor número de emplacamentos. 
             Answer: SELECT municipio, COUNT(*) AS quantidade_motos_emplacadas FROM [tbl_emplacamento] WHERE ano_emplacamento = 2024 AND modelo_tipo LIKE '%Moto%' GROUP BY municipio ORDER BY quantidade_motos_emplacadas DESC;
             
             3. Quais são os municípios com o maior número de concessionárias registradas no banco de dados? Retorne a contagem total de concessionárias por município, ordenada do maior para o menor número.?
             Answer: SELECT municipio, COUNT(*) AS quantidade_concessionarias FROM [tbl_concessionarias] GROUP BY municipio ORDER BY quantidade_concessionarias DESC;

             4. Plot the distribution of income over time 
             Answer: SELECT income, COUNT(*) as count FROM users WHERE income IS NOT NULL AND income != "" AND income != "N/A" GROUP BY income 
             
             5. How many motocycles were registered in 2014?
             Answer: SELECT COUNT(*) AS quantidade_motos_emplacadas 
                            FROM [tbl_emplacamento] 
                            WHERE ano_emplacamento = 2014 
                            AND modelo_tipo LIKE '%Moto%';

             6. Quais foram os 2 modelos de moto mais vendidos em 2023 e 2024 no estado de SP?
             Answer: SELECT TOP 2 WITH TIES 
                            ano_emplacamento, 
                            modelo, 
                            COUNT(*) AS total_vendas
                     FROM [tbl_emplacamento]
                     WHERE estado = 'SP'
                     AND ano_emplacamento IN (2023, 2024)
                     AND grupo_modelo_veiculo = 'MOTO'  -- Filtra apenas motos
                     GROUP BY ano_emplacamento, modelo
                     ORDER BY ano_emplacamento, total_vendas DESC;
             
             7. Quantos modelos de motocicletas foram registradas em São Paulo em janeiro de 2023 e quais foram as métricas governamentais relacionadas a motocicletas?
             Answer: SELECT em.ano_emplacamento,
                        em.mes_emplacamento,
                        em.estado,
                        em.municipio,
                        em.fabricante,
                        em.modelo_tipo,
                        COUNT(em.modelo) AS total_vehicles_emplacados,
                        SUM(COALESCE(mm.valor, 0)) AS metric_value,
                        mm.categoria,
                        mm.orgao
                    FROM tbl_emplacamento_sample em
                    LEFT JOIN br_gov_motorcycle_metrics_sample mm
                        ON em.ano_emplacamento = mm.ano
                        AND em.mes_emplacamento = mm.mes
                        AND em.estado = mm.unidade  -- Assuming 'unidade' corresponds to state
                    WHERE em.ano_emplacamento IS NOT NULL
                    GROUP BY 
                        em.ano_emplacamento, 
                        em.mes_emplacamento, 
                        em.estado, 
                        em.municipio, 
                        em.fabricante, 
                        em.modelo_tipo, 
                        mm.categoria, 
                        mm.orgao
                    ORDER BY em.ano_emplacamento DESC, em.mes_emplacamento DESC;

             8. calcular o Market Share da Honda em relação às demais fabricantes nos estados do Sudeste:
             Answer: SELECT TOP (10) estado,
                            COUNT(CASE WHEN fabricante = 'HONDA' THEN 1 END) AS total_honda,
                            COUNT(*) AS total_geral,
                            (COUNT(CASE WHEN fabricante = 'HONDA' THEN 1 END) * 100.0 / COUNT(*)) AS market_share_honda
                    FROM [tbl_emplacamento] 
                    WHERE estado IN ('SP', 'RJ', 'MG', 'ES') -- Filtrar os estados desejados
                    GROUP BY estado
                    ORDER BY market_share_honda DESC;

             9. Ranking de vendas de motocicletas por modelo na cidade de São Paulo/SP
             Answer: SELECT TOP (10) modelo,
                        COUNT(*) AS total_vendas,
                        RANK() OVER (ORDER BY COUNT(*) DESC) AS ranking
                    FROM [tbl_emplacamento] 
                    WHERE municipio LIKE '%Sao Paulo%' AND estado = 'SP' AND modelo_tipo LIKE  '%MOTO%'
                    GROUP BY modelo
                    ORDER BY total_vendas DESC;
             10. Me dê uma visão histórica da participação de mercado das principais marcas de motocicletas no Brasil.
             Answer: WITH cte_market_share AS (
                            SELECT
                                            fabricante,
                                            ano_emplacamento,
                                            COUNT(*)*100.0 / SUM(COUNT(*)) OVER(PARTITION BY ano_emplacamento) AS market_share,
                                            ROW_NUMBER() OVER(PARTITION BY ano_emplacamento ORDER BY COUNT(*) DESC) ranking
                            FROM tbl_emplacamento
                            GROUP BY fabricante, ano_emplacamento
                    )

                    SELECT 
                            fabricante,
                            ano_emplacamento,
                            market_share
                    FROM cte_market_share
                    WHERE ranking <= 3 -- traz o top 3 por ano
                    ORDER BY ano_emplacamento DESC
             11. Qual a variação de Market Share em pontos percentuais da Honda comparando o ano de 2019 Vs. 2024 ?
             Answer: WITH market_share AS (
                        SELECT 
                            ano_emplacamento,
                            COUNT(CASE WHEN fabricante = 'HONDA' THEN 1 END) * 100.0 / COUNT(*) AS market_share
                        FROM tbl_emplacamento
                        WHERE ano_emplacamento IN (2019, 2024)
                        GROUP BY ano_emplacamento
                    )
                    SELECT 
                        ms_2024.ano_emplacamento AS ano_2024,
                        ms_2024.market_share AS market_share_2024,
                        ms_2019.market_share AS market_share_2019,
                        ms_2024.market_share - ms_2019.market_share AS variacao_market_share
                    FROM market_share ms_2024
                    JOIN market_share ms_2019 ON ms_2024.ano_emplacamento = 2024 AND ms_2019.ano_emplacamento = 2019;

            12. Quais as cidades do Brasil que a Honda mais cresceu em vendas comparando o ano de 2024 Vs. 2023 ? Quando tiver uma pergunta similar ao contexto com essa cria uma query similar a query a seguir.
             Answer: WITH vendas_por_cidade AS (
                    SELECT 
                        municipio,
                        ano_emplacamento,
                        COUNT(*) AS total_vendas
                    FROM tbl_emplacamento
                    WHERE fabricante = 'HONDA' AND ano_emplacamento IN (2023, 2024)
                    GROUP BY municipio, ano_emplacamento
                ),
                crescimento AS (
                    SELECT 
                        v2024.municipio,
                        v2024.total_vendas AS vendas_2024,
                        v2023.total_vendas AS vendas_2023,
                        (v2024.total_vendas - v2023.total_vendas) AS crescimento_absoluto,
                        ((v2024.total_vendas - v2023.total_vendas) * 100.0 / NULLIF(v2023.total_vendas, 0)) AS crescimento_percentual
                    FROM vendas_por_cidade v2024
                    LEFT JOIN vendas_por_cidade v2023 
                        ON v2024.municipio = v2023.municipio 
                        AND v2023.ano_emplacamento = 2023
                    WHERE v2024.ano_emplacamento = 2024
                )
                SELECT 
                    municipio,
                    crescimento_absoluto,
                    crescimento_percentual
                FROM crescimento
                ORDER BY crescimento_absoluto DESC
             
             13. No estado do Amapá, qual marca teve o maior market share dentre todos os segmentos? 
             Answer: WITH market_share_por_marca AS (
                        SELECT 
                            fabricante,
                            COUNT(*) AS total_vendas,
                            COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () AS market_share
                        FROM tbl_emplacamento
                        WHERE estado = 'AP' -- Filtra apenas o estado do Amapá
                        GROUP BY fabricante
                    )
                    SELECT 
                        fabricante,
                        total_vendas,
                        market_share
                    FROM market_share_por_marca
                    ORDER BY market_share DESC
             
             15. Quando foi o mês com maior emplacamento mensal da categoria scooter?
             Answer: SELECT TOP 1 mes_emplacamento, ano_emplacamento, COUNT(*) AS total_emplacamentos
FROM tbl_emplacamento
WHERE segmento LIKE '%scooter%'
GROUP BY mes_emplacamento, ano_emplacamento
ORDER BY total_emplacamentos DESC;

               
             THE RESULTS SHOULD ONLY BE IN THE FOLLOWING FORMAT, SO MAKE SURE TO ONLY GIVE TWO OR THREE COLUMNS:
             [[x, y]]
             or 
             [[label, x, y]]

             14.Quantas motos importadas foram emplacadas em Julho/24?
             Answer: SELECT COUNT(*) AS quantidade_motos_importadas 
                            FROM [tbl_emplacamento] 
                            WHERE ano_emplacamento = 2024 
                            AND mes_emplacamento = 7 
                            AND modelo_tipo LIKE '%Moto%' 
                            AND modelo LIKE 'I/%';

             Always when the question is about city, the table column with this information will be in "municipio".  
             Use RANK() OVER when the question is about ranking.
             When the question is about ranking, return just the top 5 or 10 first itens, and NOT all the rank.
             When the question has something about "motocicleta" filter by "modelo_tipo" because there you will find information about like "moto".
             For questions like "plot a distribution of the fares for men and women", count the frequency of each fare and plot it. The x axis should be the fare and the y axis should be the count of people who paid that fare.
             SKIP ALL ROWS WHERE ANY COLUMN IS NULL or "N/A" or "".
             Use RANK() or DENSE_RANK() to rank when the question is about per year or per period.
             Do not EVER use OFFSET or FETCH NEXT.
             Do not ever use ``` on the query generation, because this can cause an error on the database
             If the question mention the amount of results, do your best to return just the asked amount and not more results.
             Just give the query string. Do not format it. Make sure to use the correct spellings of nouns as provided in the unique nouns list. All the table and column names should be enclosed in backticks.
             Para buscas textuais, SEMPRE use LIKE '%<termo>%' em vez de '=' para garantir busca parcial.
             Nunca use '=' para comparação de texto em colunas de string. Sempre prefira LIKE '%<termo>%'.
             Para múltiplos valores, use 'LIKE' combinado com 'OR'. 
             Sempre adicione '%' no início e no fim do valor pesquisado.
             Quando a pergunta envolver ano, mes ou ano/mes, SEMPRE ordenar pela coluna de ano e/ou mes.
             '''),
             
             ("human", '''===Database schema: {schema} 
             ===User question: {question}
             ===Relevant tables and columns: {parsed_question}
             ===Unique nouns in relevant tables: {unique_nouns}
             Generate a valid Azure SQL query.'''),
        ])

        try:
            # ✅ Generate SQL Query with chat memory
            response = self.llm_manager.invoke(prompt, schema=schema, question=question, parsed_question=parsed_question, unique_nouns=unique_nouns, chat_history=chat_history)

            if response.strip() == "NOT_ENOUGH_INFO":
                self.memory.save_context({"input": question}, {"output": "⚠️ LLM couldn't generate enough information to create an SQL query."})
                return {"sql_query": "NOT_RELEVANT"}

            # ✅ Store successful SQL query in memory
            self.memory.save_context({"input": question}, {"output": response})

            return {"sql_query": response}

        except Exception as e:
            error_message = f"❌ Error generating SQL: {e}"
            self.memory.save_context({"input": question}, {"output": error_message})  # ✅ Store error in memory
            print(error_message)
            return {"sql_query": "ERROR"}

    def validate_and_fix_sql(self, state: dict) -> dict:
        """Validate and fix the generated SQL query."""
        # sql_query = state['sql_query']

        # if sql_query == "ERROR":
        #     return {"sql_query": "ERROR", "sql_valid": False}
        sql_query = state['sql_query']

        if sql_query == "NOT_RELEVANT":
            return {"sql_query": "NOT_RELEVANT", "sql_valid": False}

        schema = self.db_manager.get_schema()

        prompt = ChatPromptTemplate.from_messages([
            # ("system", '''You are an AI assistant that validates and fixes SQL queries.'''),
            ("system", r'''
            You are an AI assistant that validates and fixes SQL queries for an Azure SQL Database. Your task is to:
             1. Table and column names do NOT use backticks (`). Use normal SQL syntax.  
             2. Only fix actual SQL errors. Do NOT change correct table names, column names, or query structure.  
             3. Return ONLY the corrected SQL query string with no extra text.  
             4. If the input SQL query is already correct, return it unchanged.
             5. Check if the SQL query is valid.
             6. Ensure all table and column names are correctly spelled and exist in the schema. All the table and column names should be enclosed in backticks.
             7. If there are any issues, fix them and provide the corrected SQL query.
             8. If no issues are found, return the original query.
             Example Fixes:
        
             Incorrect SQL:  
            ```sql
            SELECT COUNT(*) FROM `tbl_emplacamento` WHERE `ano_emplacamento` = 2024;
            ```
            
             Corrected SQL:  
            ```sql
            SELECT COUNT(*) FROM [tbl_emplacamento] WHERE ano_emplacamento = 2024;
            ```
            
             Incorrect SQL:  
            ```sql
            SELECT * FROM users WHERE income > 50000;
            ```
            
             Corrected SQL (no changes needed):  
            ```sql
            SELECT * FROM users WHERE income > 50000;
            ```

             Respond in JSON format with the following structure. Only respond with the JSON:
            {{
                "valid": boolean,
                "issues": string or null,
                "corrected_query": string
            }}
            '''),
            # ("human", '''===Database schema:\n{schema}\n\n===Generated SQL query:\n{sql_query}\n\nRespond in JSON format with corrected SQL query.''')
            ("human", '''
             ===Database schema:{schema}
             ===Generated SQL query:{sql_query}

            Respond in JSON format with the following structure. Only respond with the JSON:
            {{
                "valid": boolean,
                "issues": string or null,
                "corrected_query": string
            }}

            For example:
            1. {{
                "valid": true,
                "issues": null,
                "corrected_query": "None"
            }}
                        
            2. {{
                "valid": false,
                "issues": "Column USERS does not exist",
                "corrected_query": "SELECT * FROM \[users\] WHERE age > 25"
            }}

            3. {{
                "valid": false,
                "issues": "Column names and table names should be enclosed in backticks if they contain spaces or special characters",
                "corrected_query": "SELECT * FROM \[gross income\] WHERE \age\ > 25"
            }}
                        
            '''),
        ])

        output_parser = JsonOutputParser()

        response = self.llm_manager.invoke(prompt, schema=schema, sql_query=sql_query)
        result = output_parser.parse(response)

        if result.get("valid") and result.get("issues") is None:
            return {"sql_query": sql_query, "sql_valid": True}
        else:
            return {
                "sql_query": result.get("corrected_query", sql_query),
                "sql_valid": result.get("valid", False),
                "sql_issues": result.get("issues", [])
            }

    def execute_sql(self, state: dict) -> dict:
        """Execute SQL query and return results in a pandas-compatible format."""
        query = state['sql_query']
        
        if query == "NOT_RELEVANT":
            return {"results": "NOT_RELEVANT"}
        
        try:
            cursor = self.db_manager.get_connection().cursor()
            cursor.execute(query)

            # Fetch column names
            columns = [desc[0] for desc in cursor.description]
            
            # Fetch results and convert each row to a dictionary
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            # Convert to DataFrame (for Streamlit compatibility)
            df = pd.DataFrame(rows)
            
            return {"results": df}
        
        except Exception as e:
            return {"error": str(e)}

    def format_results(self, state: dict) -> dict:
        """Format query results into a human-readable response."""
        question = state.get('question', "Unknown Question")  # ✅ FIX: Ensure question exists
        results = state.get('results', None)  # ✅ FIX: Default to None if missing

        # ✅ FIX: If results are missing, return a fallback response
        if results is None:
            error_message = "❌ ERROR: 'results' key is missing in state. Returning fallback message."
            self.remember(question, error_message)  # ✅ Store error in memory
            print(error_message)
            return {"answer": "An error occurred while retrieving the data. Please try again."}

        if results == "NOT_RELEVANT":
            self.remember(question, "⚠️ No relevant answer found for this question.")
            return {"answer": "Sorry, I can only give answers relevant to the database."}

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an AI assistant that formats database query results into a human-readable response. Give a conclusion to the user's question based on the query results. Do not give the answer in markdown format. Only give the answer in one line."),
            ("human", "User question: {question}\n\nQuery results: {results}\n\nFormatted response:")
        ])

        try:
            response = self.llm_manager.invoke(prompt, question=question, results=results)

            # ✅ Store formatted answer in memory
            self.remember(question, f"📢 Formatted Answer: {response}")

            return {"answer": response}

        except Exception as e:
            error_message = f"❌ ERROR: Failed to format results - {e}"
            self.remember(question, error_message)  # ✅ Store error in memory
            print(error_message)
            return {"answer": "An error occurred while formatting the response."}
    
    def choose_visualization(self, state: dict) -> dict:
        """Choose an appropriate visualization for the data."""
        question = state.get('question', "Unknown Question")  # ✅ FIX: Ensure question exists
        sql_query = state.get('sql_query', "UNKNOWN QUERY")  # ✅ FIX: Ensure sql_query exists
        results = state.get("results", None)
        print("teste", results)

        # ✅ Fix: Ensure results is not a DataFrame before comparison
        if isinstance(results, str) and results == "NOT_RELEVANT":
            return {"visualization": "none", "visualization_reasoning": "No visualization needed for irrelevant questions."}

        prompt = ChatPromptTemplate.from_messages([
            # ("system", '''You are an AI assistant that recommends appropriate data visualizations.'''),
            ("system", r'''You are an AI assistant that recommends appropriate data visualizations. Based on the user's question, SQL query, and query results, suggest the most suitable type of graph or chart to visualize the data. If no visualization is appropriate, indicate that.
                        Available chart types and their use cases:
                        - Bar Graphs: Best for comparing categorical data or showing changes over time when categories are discrete and the number of categories is more than 2. Use for questions like "What are the sales figures for each product?" or "How does the population of cities compare? or "What percentage of each city is male?"
                        - Horizontal Bar Graphs: Best for comparing categorical data or showing changes over time when the number of categories is small or the disparity between categories is large. Use for questions like "Show the revenue of A and B?" or "How does the population of 2 cities compare?" or "How many men and women got promoted?" or "What percentage of men and what percentage of women got promoted?" when the disparity between categories is large.
                        - Scatter Plots: Useful for identifying relationships or correlations between two numerical variables or plotting distributions of data. Best used when both x axis and y axis are continuous. Use for questions like "Plot a distribution of the fares (where the x axis is the fare and the y axis is the count of people who paid that fare)" or "Is there a relationship between advertising spend and sales?" or "How do height and weight correlate in the dataset? Do not use it for questions that do not have a continuous x axis."
                        - Pie Charts: Ideal for showing proportions or percentages within a whole. Use for questions like "What is the market share distribution among different companies?" or "What percentage of the total revenue comes from each product?"
                        - Line Graphs: Best for showing trends and distributionsover time. Best used when both x axis and y axis are continuous. Used for questions like "How have website visits changed over the year?" or "What is the trend in temperature over the past decade?". Do not use it for questions that do not have a continuous x axis or a time based x axis.

                        Consider these types of questions when recommending a visualization:
                        1. Aggregations and Summarizations (e.g., "What is the average revenue by month?" - Line Graph)
                        2. Comparisons (e.g., "Compare the sales figures of Product A and Product B over the last year." - Line or Column Graph)
                        3. Plotting Distributions (e.g., "Plot a distribution of the age of users" - Scatter Plot)
                        4. Trends Over Time (e.g., "What is the trend in the number of active users over the past year?" - Line Graph)
                        5. Proportions (e.g., "What is the market share of the products?" - Pie Chart)
                        6. Correlations (e.g., "Is there a correlation between marketing spend and revenue?" - Scatter Plot)

                        Provide your response in the following format:
                        Always return the values and create the visualization in descendent order.
                        Recommended Visualization: [Chart type or "None"]. ONLY use the following names: bar, horizontal_bar, line, pie, scatter, none
                        Reason: [Brief explanation for your recommendation]
                        '''),
            ("human", '''User question: {question}\nSQL query: {sql_query}\nQuery results: {results}\n\nRecommend a visualization:'''),
        ])

        response = self.llm_manager.invoke(prompt, question=question, sql_query=sql_query, results=results)

        '''
        strip() removes normal leading/trailing spaces.
        .replace("\xa0", "") removes non-breaking spaces.
        .replace("\t", "") removes tabs.
        .replace("\n", "") removes newlines.
        .replace("\r", "") removes carriage returns.
        '''
        lines = response.split('\n')
        visualization = lines[0].split(': ')[1]
        reason = lines[1].split(': ')[1]
        clean_visualization = visualization.strip().replace("\xa0", "").replace("\t", "").replace("\n", "").replace("\r", "")
        print(f"Visualization key 2: '{clean_visualization}'") # REMOVE BEFORE GO TO PRODUCTION

        return {"visualization": clean_visualization, "visualization_reason": reason}