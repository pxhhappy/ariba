import sys
import os
import pickle
from ariba import reference_data

class Error (Exception): pass


class RefPreparer:
    def __init__(self,
        fasta_files,
        metadata_tsv_files,
        extern_progs,
        version_report_lines=None,
        min_gene_length=6,
        max_gene_length=10000,
        genetic_code=11,
        cdhit_min_id=0.9,
        cdhit_min_length=0.9,
        run_cdhit=True,
        clusters_file=None,
        threads=1,
        verbose=False,
    ):
        self.extern_progs = extern_progs

        if version_report_lines is None:
            self.version_report_lines = []
        else:
            self.version_report_lines = version_report_lines

        self.fasta_files = fasta_files
        self.metadata_tsv_files = metadata_tsv_files
        self.min_gene_length = min_gene_length
        self.max_gene_length = max_gene_length
        self.genetic_code = genetic_code
        self.cdhit_min_id = cdhit_min_id
        self.cdhit_min_length = cdhit_min_length
        self.run_cdhit = run_cdhit
        self.clusters_file = clusters_file
        self.threads = threads
        self.verbose = verbose


    def _write_info_file(self, outfile):
        with open(outfile, 'w') as fout:
            for filename in self.fasta_files:
                print('input fasta file:', filename, sep='\t', file=fout)

            for filename in self.metadata_tsv_files:
                print('input tsv file:', filename, sep='\t', file=fout)

            print('genetic_code', self.genetic_code, sep='\t', file=fout)


    @staticmethod
    def _rename_clusters(clusters_in):
        new_clusters = {}
        key_count = {}
        min_prefix_length = 3

        for old_name, name_set in sorted(clusters_in.items()):
            names_before_dots = {}
            for name in name_set:
                if '.' in name:
                    prefix = name.split('.')[0]
                    if len(prefix) >= min_prefix_length:
                        names_before_dots[prefix] = names_before_dots.get(prefix, 0) + 1

            if len(names_before_dots) == 0:
                new_key = 'cluster'
            elif len(names_before_dots) == 1:
                new_key = list(names_before_dots.keys())[0]
                if sum(list(names_before_dots.values())) < len(name_set):
                    new_key += '+'
            else:
                common_prefix = os.path.commonprefix(list(names_before_dots.keys()))
                if common_prefix == '' or len(common_prefix) < min_prefix_length:
                    max_value = max(list(names_before_dots.values()))
                    possible_keys = [x for x in names_before_dots if names_before_dots[x] == max_value]
                    possible_keys.sort()
                    new_key = possible_keys[0] + '+'
                else:
                    new_key = common_prefix + '-'

            if new_key in key_count:
                if new_key in new_clusters:
                    assert key_count[new_key] == 1
                    assert new_key + '_1' not in new_clusters
                    new_clusters[new_key + '_1'] = new_clusters[new_key]
                    del new_clusters[new_key]

                key_count[new_key] += 1
                new_name = new_key + '_' + str(key_count[new_key])
            else:
                key_count[new_key] = 1
                new_name = new_key

            assert new_name not in new_clusters
            new_clusters[new_name] = name_set


        return new_clusters


    def run(self, outdir):
        original_dir = os.getcwd()

        if os.path.exists(outdir):
            raise Error('Error! Output directory ' + outdir + ' already exists. Cannot continue')

        try:
            os.mkdir(outdir)
        except:
            raise Error('Error making output directory ' + outdir + '. Cannot continue')

        with open(os.path.join(outdir, '00.version_info.txt'), 'w') as f:
            print('ARIBA run with this command:', file=f)
            print(' '.join([sys.argv[0]] + ['prepareref'] + sys.argv[1:]), file=f)
            print('from this directory:', original_dir, file=f)
            print(file=f)
            print(*self.version_report_lines, sep='\n', file=f)

        self._write_info_file(os.path.join(outdir, '00.info.txt'))

        self.refdata = reference_data.ReferenceData(
            self.fasta_files,
            self.metadata_tsv_files,
            min_gene_length=self.min_gene_length,
            max_gene_length=self.max_gene_length,
            genetic_code=self.genetic_code,
        )

        if self.verbose:
            print('\nLoading and checking input data', flush=True)

        self.refdata.rename_sequences(os.path.join(outdir, '00.rename_info'))
        self.refdata.sanity_check(os.path.join(outdir, '01.filter'))

        if self.verbose:
            print('\nRunning cdhit', flush=True)
        cdhit_outprefix = os.path.join(outdir, '02.cdhit')

        clusters = self.refdata.cluster_with_cdhit(
            cdhit_outprefix,
            seq_identity_threshold=self.cdhit_min_id,
            threads=self.threads,
            length_diff_cutoff=self.cdhit_min_length,
            nocluster=not self.run_cdhit,
            verbose=self.verbose,
            clusters_file=self.clusters_file,
        )

        clusters = self._rename_clusters(clusters)
        reference_data.ReferenceData.write_cluster_allocation_file(clusters, cdhit_outprefix + '.clusters.tsv')

        if self.verbose:
            print('\nWriting clusters to file.', len(clusters), 'in total', flush=True)

        clusters_pickle_file = cdhit_outprefix + '.clusters.pickle'

        with open(clusters_pickle_file, 'wb') as f:
            pickle.dump(clusters, f)

