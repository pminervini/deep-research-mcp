ollama list | tail -n +2 | awk '{print $1}' | while read -r model; do
  ollama pull $model
done
