ARCHIVO = "shorts_engine/gemini_ia.py"
CAMBIOS = [
    (
        '        self.key_latency: Dict[int, float] = {idx: 0.5 for idx in range(len(self.api_keys))}',
        '        self.key_latency: Dict[int, float] = {idx: 0.5 for idx in range(len(self.api_keys))}\n        self.last_probe_cache: Dict[str, Tuple[float, List[int]]] = {}'
    ),
    (
        '    def fast_probe_accounts(self, target_model: str) -> List[int]:\n        """\n        Ejecuta un micro-ping paralelo en <800ms sobre todas las cuentas para `target_model`.\n        Devuelve la lista de índices de cuentas VIVAS ordenadas por menor latencia.\n        """\n        async def _run_probes():\n            tasks = [self._probe_single_key(idx, target_model) for idx in range(len(self.api_keys))]\n            return await asyncio.gather(*tasks)\n\n        try:\n            loop = asyncio.new_event_loop()\n            asyncio.set_event_loop(loop)\n            results = loop.run_until_complete(_run_probes())\n        finally:\n            try:\n                loop.close()\n            except Exception:\n                pass\n\n        vivas = [idx for idx, ok, _ in sorted(results, key=lambda x: x[2]) if ok]\n        return vivas',
        '    def fast_probe_accounts(self, target_model: str) -> List[int]:\n        """\n        Ejecuta un micro-ping paralelo en <800ms sobre todas las cuentas para `target_model`.\n        Devuelve la lista de índices de cuentas VIVAS ordenadas por menor latencia.\n        Usa caché de 180s para evitar re-probar cuentas que ya respondieron OK recientemente.\n        """\n        # Retorno rápido en caché si el último probe exitoso fue hace menos de 180s\n        cached = self.last_probe_cache.get(target_model)\n        if cached:\n            ts_cache, lista_previa = cached\n            if (time.time() - ts_cache) < 180.0:\n                vivas_ahora = [idx for idx in lista_previa if self._is_available(idx, target_model)]\n                if vivas_ahora:\n                    return vivas_ahora\n\n        async def _run_probes():\n            tasks = [self._probe_single_key(idx, target_model) for idx in range(len(self.api_keys))]\n            return await asyncio.gather(*tasks)\n\n        try:\n            loop = asyncio.new_event_loop()\n            asyncio.set_event_loop(loop)\n            results = loop.run_until_complete(_run_probes())\n        finally:\n            try:\n                loop.close()\n            except Exception:\n                pass\n\n        vivas = [idx for idx, ok, _ in sorted(results, key=lambda x: x[2]) if ok]\n        if vivas:\n            self.last_probe_cache[target_model] = (time.time(), vivas)\n        return vivas'
    ),
    (
        '        self.cooldown_until.clear()\n        self.unsupported_pairs.clear()\n        self.paid_tier_only.clear()',
        '        self.cooldown_until.clear()\n        self.unsupported_pairs.clear()\n        self.paid_tier_only.clear()\n        self.last_probe_cache.clear()'
    ),
]
