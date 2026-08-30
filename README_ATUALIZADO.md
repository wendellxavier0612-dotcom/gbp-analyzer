# GBP Analyzer — atualização

Esta versão amplia a análise usando a mesma chave `SERPAPI_KEY` do projeto.

## O que foi alterado

- Enriquecimento do resultado do Google Maps com consulta de `type=place`, reduzindo a perda de descrição, links e outros campos que nem sempre aparecem na busca inicial.
- Coleta separada de mídia do Google Maps: fotos, vídeos e conteúdo da categoria **By owner / Do proprietário**.
- Exibição de galeria de fotos e vídeos na interface.
- Campo de imagem de perfil/logo: usa um logo explicitamente retornado pela fonte, quando disponível; caso contrário, usa a foto de perfil do Instagram confirmado como fallback.
- Avaliações: coleta uma amostra pública para identificar avaliações sem comentário e sem resposta e registra datas para acompanhar tendência quando houver dados suficientes.
- Posts do Google: consulta posts públicos do proprietário e mostra atividade recente.
- Instagram: procura primeiro o perfil com `site:instagram.com`, faz um score de correspondência e somente aceita o candidato se a correspondência for suficiente; depois consulta a API `instagram_profile` para obter bio, seguidores, seguindo, publicações, foto de perfil, conta profissional/empresarial, verificação e posts.
- “Não há dados” continua sendo diferente de “0”: quando a fonte não devolve informação suficiente, o critério fica como **Não verificado** com mensagem explícita.

## Instalação

```bash
pip install -r requirements.txt
playwright install chromium
```

Crie/edite `.env` e coloque sua chave:

```env
SERPAPI_KEY=sua_chave
```

Depois:

```bash
python app.py
```

Abra `http://127.0.0.1:5000`.

## Observação importante

A contagem de fotos/vídeos é baseada na mídia efetivamente recuperada pela API na consulta/paginação utilizada. O sistema não inventa um número quando a fonte não entrega uma contagem total confiável.

Os critérios que dependem exclusivamente do painel autenticado do Perfil da Empresa continuam separados como itens de administrador, para não serem apresentados como se fossem dados públicos.
